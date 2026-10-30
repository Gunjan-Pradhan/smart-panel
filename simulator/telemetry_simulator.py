"""Safe synthetic telemetry simulator for the Smart Load Protection Panel.

Simulates electrical loads without mains voltage.
MANDATORY RULES:
1. All telemetry is published under topic 'simulator/dual_pzem/...' or with is_simulated=True.
2. The simulator is strictly isolated: it CAN NEVER publish to command topics ('.../relay/set').
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generator

# Channel 1: Industrial Load (provisional motor: ~125 W, ~0.95 A, 230 V, 50 Hz, PF ~0.65)
# Channel 2: Household Load (e.g. 200W resistive bulbs: ~200 W, ~0.87 A, 230 V, 50 Hz, PF ~1.0)


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
        # Baseline grid variations
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

        # Inrush transient during first 2 seconds of start
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

        # Resistive load: P = V^2 / R, PF ≈ 1.0, Q ≈ 0
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

