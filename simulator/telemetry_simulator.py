"""Safe synthetic telemetry and hardware simulator for the Smart Load Protection Panel.

MANDATORY RULES:
1. All generated data is labeled SIMULATED.
2. Adheres strictly to docs/mqtt_contract.md §5-9 (contract v1 JSON schema).
3. Publishes to:
     - panel/{DEVICE_ID}/telemetry/{ch} (1 Hz)
     - panel/{DEVICE_ID}/heartbeat      (every 10s)
     - panel/{DEVICE_ID}/status         (birth/last-will)
     - panel/{DEVICE_ID}/ack            (in response to commands)
4. Subscribes to:
     - panel/{DEVICE_ID}/cmd            (responds with execution ACK)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("simulator")


@dataclass
class ChannelState:
    ch: int
    relay_on: bool = False
    state: str = "OFF"
    energy_kwh: float = 0.0
    time_running_s: float = 0.0


@dataclass
class SyntheticTelemetryFrame:
    channel: int
    voltage_v: float
    current_a: float
    active_power_w: float
    apparent_power_va: float
    reactive_power_var: float
    power_factor: float
    frequency_hz: float
    energy_kwh: float
    relay_on: bool
    state: str
    is_simulated: bool = True


class SafeTelemetrySimulator:
    """Generates realistic synthetic data for testing without live 230V hardware."""

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)
        self.ch1_energy_kwh = 0.0
        self.ch2_energy_kwh = 0.0

    def generate_motor_frame(
        self,
        time_elapsed_s: float,
        dt_s: float = 1.0,
        running: bool = True,
    ) -> SyntheticTelemetryFrame:
        """Simulates Channel 1: Small induction motor (~125 W)."""
        v = 230.0 + self.rng.gauss(0.0, 1.2)
        f = 50.0 + self.rng.gauss(0.0, 0.03)

        if not running:
            return SyntheticTelemetryFrame(
                channel=1,
                voltage_v=round(v, 2),
                current_a=0.0,
                active_power_w=0.0,
                apparent_power_va=0.0,
                reactive_power_var=0.0,
                power_factor=1.0,
                frequency_hz=round(f, 2),
                energy_kwh=round(self.ch1_energy_kwh, 4),
                relay_on=False,
                state="OFF",
            )

        if time_elapsed_s < 2.0:
            surge_mult = 1.6 - (time_elapsed_s / 2.0) * 0.6
            i = (0.95 * surge_mult) + self.rng.gauss(0.0, 0.02)
            pf = 0.45 + self.rng.gauss(0.0, 0.02)
            state = "STARTING"
        else:
            i = 0.95 + self.rng.gauss(0.0, 0.015)
            pf = 0.68 + self.rng.gauss(0.0, 0.01)
            state = "RUNNING"

        s = v * i
        p = s * pf
        q = math.sqrt(max(0.0, s * s - p * p))
        self.ch1_energy_kwh += (p * dt_s) / (3600.0 * 1000.0)

        return SyntheticTelemetryFrame(
            channel=1,
            voltage_v=round(v, 2),
            current_a=round(i, 4),
            active_power_w=round(p, 2),
            apparent_power_va=round(s, 2),
            reactive_power_var=round(q, 2),
            power_factor=round(pf, 3),
            frequency_hz=round(f, 2),
            energy_kwh=round(self.ch1_energy_kwh, 4),
            relay_on=True,
            state=state,
        )

    def generate_bulb_frame(
        self,
        dt_s: float = 1.0,
        running: bool = True,
        wattage: float = 200.0,
    ) -> SyntheticTelemetryFrame:
        """Simulates Channel 2: Steady household resistive bulb load."""
        v = 230.0 + self.rng.gauss(0.0, 1.0)
        f = 50.0 + self.rng.gauss(0.0, 0.03)

        if not running:
            return SyntheticTelemetryFrame(
                channel=2,
                voltage_v=round(v, 2),
                current_a=0.0,
                active_power_w=0.0,
                apparent_power_va=0.0,
                reactive_power_var=0.0,
                power_factor=1.0,
                frequency_hz=round(f, 2),
                energy_kwh=round(self.ch2_energy_kwh, 4),
                relay_on=False,
                state="OFF",
            )

        r_equiv = (230.0 ** 2) / wattage
        p = (v ** 2) / r_equiv + self.rng.gauss(0.0, 0.5)
        i = p / v
        pf = 0.999
        s = v * i
        q = math.sqrt(max(0.0, s * s - p * p))
        self.ch2_energy_kwh += (p * dt_s) / (3600.0 * 1000.0)

        return SyntheticTelemetryFrame(
            channel=2,
            voltage_v=round(v, 2),
            current_a=round(i, 4),
            active_power_w=round(p, 2),
            apparent_power_va=round(s, 2),
            reactive_power_var=round(q, 2),
            power_factor=round(pf, 3),
            frequency_hz=round(f, 2),
            energy_kwh=round(self.ch2_energy_kwh, 4),
            relay_on=True,
            state="RUNNING",
        )


class ContractTelemetryGenerator:
    """Generates contract-compliant v1 telemetry payloads for dual-channel panels."""

    def __init__(self, device_id: str = "PANEL-0001", seed: int = 42) -> None:
        self.device_id = device_id
        self.rng = random.Random(seed)
        self.seq = 0
        self.boot_id = 1
        self.channels = {
            1: ChannelState(ch=1, relay_on=False, state="OFF"),
            2: ChannelState(ch=2, relay_on=False, state="OFF"),
        }

    def set_relay(self, ch: int, action: str) -> None:
        if ch not in self.channels:
            return
        c = self.channels[ch]
        if action.upper() == "ON":
            c.relay_on = True
            c.state = "STARTING" if ch == 1 else "RUNNING"
            c.time_running_s = 0.0
        elif action.upper() == "OFF":
            c.relay_on = False
            c.state = "OFF"
            c.time_running_s = 0.0

    def generate_packet(
        self,
        ch: int,
        dt_s: float = 1.0,
        scenario: str = "NORMAL",
    ) -> Dict[str, Any]:
        """Generate a contract v1 telemetry JSON packet.

        Scenarios:
          - NORMAL: Realistic standard motor (CH1) and resistive bulb (CH2)
          - OVERCURRENT: Surge exceeding channel trip limits
          - VOLTAGE_SAG: Voltage drop below 180V (< undervoltage limit)
          - VOLTAGE_SWELL: Voltage swell above 265V (> overvoltage limit)
          - POOR_PF: Deteriorated power factor (< 0.50)
        """
        self.seq += 1
        c = self.channels[ch]

        # Base nominal grid values
        v = 230.0 + self.rng.gauss(0.0, 1.0)
        f = 50.0 + self.rng.gauss(0.0, 0.02)

        # Apply grid voltage fault scenarios
        if scenario == "VOLTAGE_SAG":
            v = 165.0 + self.rng.gauss(0.0, 2.0)
        elif scenario == "VOLTAGE_SWELL":
            v = 278.0 + self.rng.gauss(0.0, 2.0)

        # If relay is OFF, current and power are zero
        if not c.relay_on:
            c.state = "OFF"
            return {
                "v": round(v, 2),
                "i": 0.0,
                "p": 0.0,
                "pf": 1.0,
                "f": round(f, 2),
                "e_kwh": round(c.energy_kwh, 4),
                "relay": False,
                "state": "OFF",
                "ts": int(time.time()),
                "buffered": False,
                "clock_synced": True,
                "seq": self.seq,
                "boot_id": self.boot_id,
            }

        # Relay is ON: simulate load dynamics
        c.time_running_s += dt_s

        if ch == 1:
            # Channel 1: Induction Motor (~125 W nominal, inrush decay during first 2s)
            if c.time_running_s < 2.0 and scenario != "OVERCURRENT":
                surge_mult = 1.6 - (c.time_running_s / 2.0) * 0.6
                i = (0.95 * surge_mult) + self.rng.gauss(0.0, 0.02)
                pf = 0.45 + self.rng.gauss(0.0, 0.02)
                c.state = "STARTING"
            else:
                i = 0.95 + self.rng.gauss(0.0, 0.015)
                pf = 0.68 + self.rng.gauss(0.0, 0.01)
                c.state = "RUNNING"

            if scenario == "OVERCURRENT":
                i = 18.5 + self.rng.gauss(0.0, 0.5)  # Beyond 16A hard cap
                c.state = "RUNNING"
            elif scenario == "POOR_PF":
                pf = 0.32 + self.rng.gauss(0.0, 0.02)

            p = v * i * pf
        else:
            # Channel 2: Household Sensitive / Resistive Load (~200 W nominal)
            if scenario == "OVERCURRENT":
                i = 12.5 + self.rng.gauss(0.0, 0.3)  # Beyond 10A hard cap
                p = v * i * 0.98
                pf = 0.98
            elif scenario == "POOR_PF":
                i = 1.2
                pf = 0.35
                p = v * i * pf
            else:
                p = 200.0 + self.rng.gauss(0.0, 1.0)
                pf = 0.999
                i = p / v
            c.state = "RUNNING"

        # Accumulate energy
        c.energy_kwh += (p * dt_s) / (3600.0 * 1000.0)

        return {
            "v": round(v, 2),
            "i": round(max(0.0, i), 3),
            "p": round(max(0.0, p), 2),
            "pf": round(min(1.0, max(0.0, pf)), 3),
            "f": round(f, 2),
            "e_kwh": round(c.energy_kwh, 4),
            "relay": True,
            "state": c.state,
            "ts": int(time.time()),
            "buffered": False,
            "clock_synced": True,
            "seq": self.seq,
            "boot_id": self.boot_id,
        }

    def generate_heartbeat(self, uptime_s: int) -> Dict[str, Any]:
        """Contract v1 heartbeat payload."""
        return {
            "online": True,
            "uptime": uptime_s,
            "wifi_rssi": -62 + self.rng.randint(-3, 3),
            "free_heap": 182000 + self.rng.randint(-2000, 2000),
            "ch1_state": self.channels[1].state,
            "ch2_state": self.channels[2].state,
            "clock_synced": True,
            "boot_id": self.boot_id,
            "simulated": True,
        }


class MqttPanelSimulator:
    """Simulates physical ESP32 panel over real MQTT broker.

    - Subscribes to commands on panel/{DEVICE_ID}/cmd
    - Dispatches execution ACKs on panel/{DEVICE_ID}/ack
    - Publishes dual-channel telemetry at 1 Hz on panel/{DEVICE_ID}/telemetry/{ch}
    - Publishes heartbeats at 0.1 Hz on panel/{DEVICE_ID}/heartbeat
    """

    def __init__(
        self,
        device_id: str = "PANEL-0001",
        host: str = "127.0.0.1",
        port: int = 1883,
        scenario: str = "NORMAL",
    ) -> None:
        self.device_id = device_id
        self.host = host
        self.port = port
        self.scenario = scenario
        self.generator = ContractTelemetryGenerator(device_id=device_id)
        self.client: Optional[Any] = None
        self.running = False
        self.start_time = time.time()

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            logger.info("Connected to MQTT broker at %s:%d as %s", self.host, self.port, self.device_id)
            cmd_topic = f"panel/{self.device_id}/cmd"
            client.subscribe(cmd_topic, qos=1)
            logger.info("Subscribed to command topic: %s", cmd_topic)

            # Publish birth status
            birth_payload = json.dumps({
                "online": True,
                "fw_version": "1.0.0-SIMULATED",
                "boot_id": self.generator.boot_id,
            })
            client.publish(f"panel/{self.device_id}/status", birth_payload, qos=1, retain=True)
        else:
            logger.error("Failed to connect to MQTT broker, rc=%d", rc)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Handle incoming command and publish ACK."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            action = payload.get("action")
            ch = int(payload.get("ch", 1))
            cmd_id = payload.get("cmd_id", "sim-cmd-0")

            logger.info("Received command on CH %d: action=%s, cmd_id=%s", ch, action, cmd_id)

            if action in ("ON", "OFF"):
                self.generator.set_relay(ch, action)
                ack_payload = {
                    "cmd_id": cmd_id,
                    "ch": ch,
                    "action": action,
                    "status": "EXECUTED",
                    "error_code": 0,
                    "state_after": action,
                    "relay_state": action == "ON",
                    "simulated": True,
                }
            elif action == "SCHEDULE_SYNC":
                schedules = payload.get("schedules", [])
                logger.info("Synchronized %d timer schedules on CH %d", len(schedules), ch)
                ack_payload = {
                    "cmd_id": cmd_id,
                    "ch": ch,
                    "action": "SCHEDULE_SYNC",
                    "status": "EXECUTED",
                    "error_code": 0,
                    "state_after": "SYNCED",
                    "simulated": True,
                }
            elif action == "RESET":
                self.generator.set_relay(1, "OFF")
                self.generator.set_relay(2, "OFF")
                ack_payload = {
                    "cmd_id": cmd_id,
                    "ch": ch,
                    "action": "RESET",
                    "status": "EXECUTED",
                    "error_code": 0,
                    "state_after": "NORMAL",
                    "simulated": True,
                }
            else:
                ack_payload = {
                    "cmd_id": cmd_id,
                    "ch": ch,
                    "action": str(action),
                    "status": "REJECTED",
                    "error_code": 1,
                    "state_after": "UNCHANGED",
                    "simulated": True,
                }

            ack_topic = f"panel/{self.device_id}/ack"
            client.publish(ack_topic, json.dumps(ack_payload), qos=1)
            logger.info("Published ACK to %s: %s", ack_topic, ack_payload["status"])

        except Exception as exc:
            logger.error("Error processing command: %s", exc)

    def start(self) -> None:
        import paho.mqtt.client as mqtt

        self.client = mqtt.Client(client_id=f"sim-{self.device_id}-{int(time.time())}")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # Set LWT (Last Will and Testament)
        lwt_payload = json.dumps({"online": False, "simulated": True})
        self.client.will_set(f"panel/{self.device_id}/status", lwt_payload, qos=1, retain=True)

        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()
        self.running = True

    def stop(self) -> None:
        if self.client and self.running:
            self.running = False
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Simulator stopped.")

    def run_loop(self, interval_s: float = 1.0, duration_s: Optional[float] = None) -> None:
        """Main loop: continuously publish 1 Hz telemetry and 10s heartbeat."""
        self.start()
        start = time.time()
        last_hb = 0.0

        try:
            while self.running:
                now = time.time()
                uptime = int(now - self.start_time)

                # 1. Publish CH1 and CH2 telemetry
                for ch in (1, 2):
                    packet = self.generator.generate_packet(
                        ch=ch,
                        dt_s=interval_s,
                        scenario=self.scenario,
                    )
                    topic = f"panel/{self.device_id}/telemetry/{ch}"
                    self.client.publish(topic, json.dumps(packet), qos=0)

                # 2. Publish heartbeat every 10 seconds
                if now - last_hb >= 10.0:
                    hb = self.generator.generate_heartbeat(uptime)
                    self.client.publish(f"panel/{self.device_id}/heartbeat", json.dumps(hb), qos=1)
                    last_hb = now

                if duration_s and (now - start) >= duration_s:
                    break

                time.sleep(interval_s)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received.")
        finally:
            self.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Smart Panel Telemetry & Command Simulator")
    parser.add_argument("--device-id", default="PANEL-0001", help="Device ID (default: PANEL-0001)")
    parser.add_argument("--host", default="127.0.0.1", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument(
        "--scenario",
        default="NORMAL",
        choices=["NORMAL", "OVERCURRENT", "VOLTAGE_SAG", "VOLTAGE_SWELL", "POOR_PF"],
        help="Simulated electrical scenario",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Publish interval in seconds")
    parser.add_argument("--duration", type=float, default=None, help="Stop after N seconds")
    args = parser.parse_args()

    print("=" * 60)
    print("  SMART LOAD PROTECTION PANEL — HARDWARE SIMULATOR")
    print(f"  Device:   {args.device_id}")
    print(f"  Scenario: {args.scenario}")
    print(f"  Target:   {args.host}:{args.port}")
    print("  Note:     ALL DATA IS SIMULATED (No 230V live hardware required)")
    print("=" * 60)

    sim = MqttPanelSimulator(
        device_id=args.device_id,
        host=args.host,
        port=args.port,
        scenario=args.scenario,
    )
    sim.run_loop(interval_s=args.interval, duration_s=args.duration)


if __name__ == "__main__":
    main()
