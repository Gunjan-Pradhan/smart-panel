"""Tests for Workstream 10: Simulator Upgrade.

Verifies:
1. Contract v1 telemetry structure and field validation.
2. Inrush decay behaviour during startup on Channel 1.
3. Relay toggle commands (ON/OFF) and state reflection.
4. Energy accumulation over time.
5. Fault scenarios:
   - OVERCURRENT produces current above hard caps.
   - VOLTAGE_SAG produces voltage < 180V.
   - VOLTAGE_SWELL produces voltage > 265V.
   - POOR_PF produces PF < 0.50.
6. Heartbeat structure and simulated flags.
7. Command handling and ACK generation.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from simulator.telemetry_simulator import (
    ContractTelemetryGenerator,
    MqttPanelSimulator,
)


@pytest.fixture
def generator():
    return ContractTelemetryGenerator(device_id="PANEL-0001", seed=42)


def test_telemetry_packet_contract_v1_fields(generator):
    """Telemetry packet contains all mandatory contract v1 fields."""
    generator.set_relay(1, "ON")
    packet = generator.generate_packet(ch=1, dt_s=1.0, scenario="NORMAL")

    required_fields = [
        "v", "i", "p", "pf", "f", "e_kwh", "relay", "state",
        "ts", "buffered", "clock_synced", "seq", "boot_id",
    ]
    for field in required_fields:
        assert field in packet, f"Missing required field: {field}"

    assert packet["relay"] is True
    assert packet["buffered"] is False
    assert packet["clock_synced"] is True
    assert packet["seq"] == 1
    assert 220.0 <= packet["v"] <= 245.0
    assert 49.0 <= packet["f"] <= 51.0


def test_relay_off_produces_zero_power(generator):
    """When relay is OFF, current and active power are 0.0."""
    generator.set_relay(1, "OFF")
    packet = generator.generate_packet(ch=1, dt_s=1.0, scenario="NORMAL")

    assert packet["relay"] is False
    assert packet["i"] == 0.0
    assert packet["p"] == 0.0
    assert packet["state"] == "OFF"


def test_motor_inrush_transient_decay(generator):
    """Channel 1 motor experiences higher current and lower PF during first 2 seconds."""
    generator.set_relay(1, "ON")

    # Inrush step 1 (t < 2s)
    pkt_inrush = generator.generate_packet(ch=1, dt_s=0.5, scenario="NORMAL")
    assert pkt_inrush["state"] == "STARTING"
    assert pkt_inrush["i"] > 1.1  # Higher surge current
    assert pkt_inrush["pf"] < 0.6  # Degraded initial PF

    # Steady-state (t >= 2.0s)
    generator.generate_packet(ch=1, dt_s=1.0, scenario="NORMAL")
    pkt_running = generator.generate_packet(ch=1, dt_s=1.0, scenario="NORMAL")
    assert pkt_running["state"] == "RUNNING"
    assert pkt_running["i"] < 1.1
    assert pkt_running["pf"] > 0.6


def test_energy_accumulation(generator):
    """Energy in kWh increases monotonically as power runs over time."""
    generator.set_relay(2, "ON")

    pkt1 = generator.generate_packet(ch=2, dt_s=1.0, scenario="NORMAL")
    pkt2 = generator.generate_packet(ch=2, dt_s=10.0, scenario="NORMAL")
    pkt3 = generator.generate_packet(ch=2, dt_s=100.0, scenario="NORMAL")

    assert pkt1["e_kwh"] < pkt2["e_kwh"] < pkt3["e_kwh"]
    assert pkt3["e_kwh"] > 0.0


def test_scenario_overcurrent(generator):
    """OVERCURRENT scenario forces current beyond hard limits (CH1 > 16A, CH2 > 10A)."""
    generator.set_relay(1, "ON")
    pkt_ch1 = generator.generate_packet(ch=1, dt_s=1.0, scenario="OVERCURRENT")
    assert pkt_ch1["i"] > 16.0, f"Expected CH1 current > 16A, got {pkt_ch1['i']}"

    generator.set_relay(2, "ON")
    pkt_ch2 = generator.generate_packet(ch=2, dt_s=1.0, scenario="OVERCURRENT")
    assert pkt_ch2["i"] > 10.0, f"Expected CH2 current > 10A, got {pkt_ch2['i']}"


def test_scenario_voltage_sag_and_swell(generator):
    """VOLTAGE_SAG drops below 180V, VOLTAGE_SWELL rises above 265V."""
    generator.set_relay(1, "ON")

    pkt_sag = generator.generate_packet(ch=1, dt_s=1.0, scenario="VOLTAGE_SAG")
    assert pkt_sag["v"] < 180.0, f"Expected sag < 180V, got {pkt_sag['v']}"

    pkt_swell = generator.generate_packet(ch=1, dt_s=1.0, scenario="VOLTAGE_SWELL")
    assert pkt_swell["v"] > 265.0, f"Expected swell > 265V, got {pkt_swell['v']}"


def test_scenario_poor_power_factor(generator):
    """POOR_PF scenario forces power factor below 0.50."""
    generator.set_relay(1, "ON")
    pkt = generator.generate_packet(ch=1, dt_s=1.0, scenario="POOR_PF")
    assert pkt["pf"] < 0.50, f"Expected poor PF < 0.50, got {pkt['pf']}"


def test_heartbeat_payload(generator):
    """Heartbeat contains online status, uptime, and simulated marker."""
    hb = generator.generate_heartbeat(uptime_s=120)
    assert hb["online"] is True
    assert hb["uptime"] == 120
    assert hb["simulated"] is True
    assert "wifi_rssi" in hb
    assert "free_heap" in hb


def test_command_ack_generation():
    """Simulator responds to commands with valid contract v1 ACKs."""
    sim = MqttPanelSimulator(device_id="PANEL-0001")
    mock_client = MagicMock()

    # Simulate ON command
    msg_on = MagicMock()
    msg_on.payload = json.dumps({"cmd_id": "test-123", "ch": 1, "action": "ON"}).encode("utf-8")
    sim._on_message(mock_client, None, msg_on)

    assert mock_client.publish.called
    topic, payload = mock_client.publish.call_args[0]
    assert topic == "panel/PANEL-0001/ack"
    ack_data = json.loads(payload)
    assert ack_data["cmd_id"] == "test-123"
    assert ack_data["status"] == "EXECUTED"
    assert ack_data["action"] == "ON"
    assert ack_data["relay_state"] is True
    assert sim.generator.channels[1].relay_on is True

