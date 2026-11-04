#include "pzem_reader.h"
#include <string.h>
#include <math.h>

#ifdef ARDUINO
#include <Arduino.h>
#include <HardwareSerial.h>

static HardwareSerial PzemSerial1(1);
static HardwareSerial PzemSerial2(2);
#endif

uint16_t pzem_calculate_crc16(const uint8_t *buffer, uint16_t len) {
    uint16_t crc = 0xFFFF;
    for (uint16_t pos = 0; pos < len; pos++) {
        crc ^= (uint16_t)buffer[pos];
        for (int i = 8; i != 0; i--) {
            if ((crc & 0x0001) != 0) {
                crc >>= 1;
                crc ^= 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

void pzem_reader_init(
    PZEMReader* reader,
    uint8_t channel,
    uint8_t uart_num,
    uint8_t rx_pin,
    uint8_t tx_pin,
    uint8_t modbus_addr
) {
    if (!reader) return;

    memset(reader, 0, sizeof(PZEMReader));
    reader->channel = channel;
    reader->uart_num = uart_num;
    reader->rx_pin = rx_pin;
    reader->tx_pin = tx_pin;
    reader->modbus_addr = modbus_addr;
    reader->injection_active = false;
    reader->has_previous_sample = false;
    reader->previous_current_a = 0.0f;

#ifdef ARDUINO
    if (uart_num == 1) {
        PzemSerial1.begin(9600, SERIAL_8N1, rx_pin, tx_pin);
    } else if (uart_num == 2) {
        PzemSerial2.begin(9600, SERIAL_8N1, rx_pin, tx_pin);
    }
#endif
}

bool pzem_validate_reading(const ElectricalReading* r, float prev_current_a, bool has_prev) {
    if (!r || !r->valid) return false;

    // Plausible AC bounds check
    if (r->voltage_v < PZEM_MIN_PLAUSIBLE_VOLTAGE || r->voltage_v > PZEM_MAX_PLAUSIBLE_VOLTAGE) {
        return false;
    }
    if (r->current_a < 0.0f || r->current_a > PZEM_MAX_PLAUSIBLE_CURRENT) {
        return false;
    }
    if (r->active_power_w < 0.0f || r->active_power_w > 15000.0f) {
        return false;
    }
    if (r->power_factor < 0.0f || r->power_factor > 1.0f) {
        return false;
    }
    if (r->frequency_hz < PZEM_MIN_PLAUSIBLE_FREQ || r->frequency_hz > PZEM_MAX_PLAUSIBLE_FREQ) {
        return false;
    }

    // Maximum plausible jump rule (rejects serial decode framing glitches e.g. 590,000 A)
    if (has_prev) {
        float jump = fabsf(r->current_a - prev_current_a);
        if (jump > PZEM_MAX_CURRENT_JUMP) {
            return false;
        }
    }

    return true;
}

bool pzem_poll_reading(PZEMReader* reader, ElectricalReading* out_reading) {
    if (!reader || !out_reading) return false;

    // Check if laboratory fault injection is active
    if (reader->injection_active) {
        *out_reading = reader->injected_reading;
        out_reading->valid = pzem_validate_reading(
            out_reading,
            reader->previous_current_a,
            reader->has_previous_sample
        );

        if (out_reading->valid) {
            reader->previous_current_a = out_reading->current_a;
            reader->has_previous_sample = true;
            reader->last_reading = *out_reading;
        }
        return out_reading->valid;
    }

#ifdef ARDUINO
    HardwareSerial* serial = (reader->uart_num == 1) ? &PzemSerial1 : &PzemSerial2;

    // Standard Modbus RTU Read Input Registers (0x04), start 0x0000, 10 registers
    uint8_t cmd[8] = {
        reader->modbus_addr, 0x04, 0x00, 0x00, 0x00, 0x0A, 0x00, 0x00
    };
    uint16_t crc = pzem_calculate_crc16(cmd, 6);
    cmd[6] = (uint8_t)(crc & 0xFF);
    cmd[7] = (uint8_t)((crc >> 8) & 0xFF);

    // Flush any pending RX bytes
    while (serial->available()) serial->read();

    // Transmit request
    serial->write(cmd, 8);
    serial->flush();

    // Read response (expected 25 bytes: addr, 0x04, 20 bytes data, 2 bytes CRC)
    uint8_t resp[32];
    uint32_t start_ms = millis();
    uint8_t bytes_read = 0;

    while (millis() - start_ms < 150) { // 150 ms timeout
        if (serial->available()) {
            resp[bytes_read++] = serial->read();
            if (bytes_read >= 25) break;
        }
    }

    if (bytes_read < 25) {
        out_reading->valid = false;
        return false;
    }

    // Verify CRC
    uint16_t resp_crc = ((uint16_t)resp[24] << 8) | resp[23];
    uint16_t calc_crc = pzem_calculate_crc16(resp, 23);
    if (resp_crc != calc_crc) {
        out_reading->valid = false;
        return false;
    }

    // Parse registers:
    // 0-1: Voltage (0.1 V)
    // 2-5: Current (0.001 A, 32-bit: low word first, high word second)
    // 6-9: Power (0.1 W, 32-bit)
    // 10-13: Energy (1 Wh, 32-bit)
    // 14-15: Frequency (0.1 Hz)
    // 16-17: Power factor (0.01)
    uint16_t raw_v = ((uint16_t)resp[3] << 8) | resp[4];
    uint32_t raw_i = ((uint32_t)resp[7] << 24) | ((uint32_t)resp[8] << 16) | ((uint32_t)resp[5] << 8) | resp[6];
    uint32_t raw_p = ((uint32_t)resp[11] << 24) | ((uint32_t)resp[12] << 16) | ((uint32_t)resp[9] << 8) | resp[10];
    uint32_t raw_e = ((uint32_t)resp[15] << 24) | ((uint32_t)resp[16] << 16) | ((uint32_t)resp[13] << 8) | resp[14];
    uint16_t raw_f = ((uint16_t)resp[17] << 8) | resp[18];
    uint16_t raw_pf = ((uint16_t)resp[19] << 8) | resp[20];

    out_reading->voltage_v = raw_v * 0.1f;
    out_reading->current_a = raw_i * 0.001f;
    out_reading->active_power_w = raw_p * 0.1f;
    out_reading->energy_kwh = raw_e * 0.001f;
    out_reading->frequency_hz = raw_f * 0.1f;
    out_reading->power_factor = raw_pf * 0.01f;
    out_reading->valid = true;
    out_reading->timestamp_s = (uint32_t)(millis() / 1000);

    // Validate bounds
    out_reading->valid = pzem_validate_reading(
        out_reading,
        reader->previous_current_a,
        reader->has_previous_sample
    );

    if (out_reading->valid) {
        reader->previous_current_a = out_reading->current_a;
        reader->has_previous_sample = true;
        reader->last_reading = *out_reading;
    }

    return out_reading->valid;
#else
    // Native stub: returns last reading
    *out_reading = reader->last_reading;
    return out_reading->valid;
#endif
}

void pzem_inject_fault(
    PZEMReader* reader,
    float v, float i, float p, float pf, float f, bool valid
) {
    if (!reader) return;
    reader->injection_active = true;
    reader->injected_reading.voltage_v = v;
    reader->injected_reading.current_a = i;
    reader->injected_reading.active_power_w = p;
    reader->injected_reading.power_factor = pf;
    reader->injected_reading.frequency_hz = f;
    reader->injected_reading.energy_kwh = 0.0f;
    reader->injected_reading.valid = valid;
    reader->injected_reading.timestamp_s = 1000;
}

void pzem_clear_injection(PZEMReader* reader) {
    if (!reader) return;
    reader->injection_active = false;
}

