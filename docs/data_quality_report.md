# Data Quality Report: Historical PZEM CSV Recordings

**Project:** Smart Load Protection Panel  
**Date:** 2026-10-30  
**Status:** Audit & Cleaning Completed  

---

## 1. Overview and Cryptographic Integrity

Three historical CSV files recorded during prototype hardware testing were audited and cleaned. In compliance with project integrity rules:
* The original CSV files in `reference/` were accessed in **read-only** mode.
* Cryptographic SHA-256 hashes were computed before and after cleaning to guarantee that the original data remained 100% unaltered.
* Cleaned datasets and structured JSON exclusion logs were saved to `data/cleaned/`.

| Original Dataset File | SHA-256 Checksum | Total Rows | Valid Retained | Excluded Glitches | Retention Rate |
|---|---|---|---|---|---|
| `pzem_training_data_20261012_115213.csv` | `E0C137EB63A41314330C9DF5DDECE4030F85CC0159E2D56ED6904A6D7672F1B2` | 239 | 237 | 2 | 99.16% |
| `home_app_training_bulb_only_20261012_123319.csv` | `A4330100E675CAE70B54DC80028FDDB59BB95B8C5116F4793C951031AD16EACC` | 136 | 132 | 4 | 97.06% |
| `pzem_training_data_20261015_160424.csv` | `9AE9667C1254E0438652291ABE1DEF28D4D58CBDDB2C83B7841C58DE98169B30` | 88 | 87 | 1 | 98.86% |

---

## 2. Root Cause Analysis of Excluded Glitches

The PZEM-004T v4 communicates via Modbus RTU over a serial UART link. When an electrical contact opens/closes or when inductive loads switch, electrical transients can corrupt byte framing. If a byte is dropped or bit-shifted, 16-bit register values decode into physically impossible magnitudes:

1. **Extreme Current Glitches:**
   * Rows with $I = 590,680.81\text{ A}$ and $I = 666,178.31\text{ A}$ were observed. These are bit-shift decode artifacts of Modbus 32-bit registers, not real physical currents.
2. **Voltage Spikes:**
   * Rows with $V = 4,740.50\text{ V}$ and $V = 643.70\text{ V}$.
3. **Power Factor Violations:**
   * Values such as $\text{PF} = 243.03$, $\text{PF} = 488.79$, and $\text{PF} = 652.63$. Physical AC power factor is mathematically bounded to $[0.0, 1.0]$.
4. **Frequency Decoding Errors:**
   * Frequencies of $182.2\text{ Hz}$, $231.6\text{ Hz}$, and $116.0\text{ Hz}$ on a standard $50\text{ Hz}$ single-phase grid.

---

## 3. Dataset Characterization & Suitability

### File 1: `pzem_training_data_20261012_115213.csv`
* **Contents:** Transition test involving a high-power steady resistive heater (~1,800 W to 2,017 W, $I \approx 8.2\text{ A}$ to $9.2\text{ A}$, $\text{PF} = 1.00$) along with lower-current baseline segments.
* **Suitability:** Suitable for **exploration** of steady-state resistive load behavior and transition detection. **Not suitable** for motor training as no inductive load was connected in this run.

### File 2: `home_app_training_bulb_only_20261012_123319.csv`
* **Contents:** Labeled household bulb combinations (`load_configuration = 'bulb_only'`). Shows steady current steps ($0.86\text{ A}$, $1.18\text{ A}$, $1.51\text{ A}$ at $228\text{ V}$, $\text{PF} = 1.00$).
* **Suitability:** **Suitable for training** household bulb baselines (resistive load profiles).

### File 3: `pzem_training_data_20261015_160424.csv`
* **Contents:** Low-noise inductive load run ($I \approx 0.59\text{ A} - 0.70\text{ A}$, active power $51\text{ W} - 147\text{ W}$, $\text{PF} \approx 0.39 - 0.93$). Zero communication errors recorded in the file.
* **Suitability:** **Suitable for motor baseline exploration** and inductive load fingerprinting.

---

## 4. Exclusion Rule Audit Trail

All exclusions were recorded in structured JSON logs:
* `data/cleaned/exclusions_pzem_training_data_20261012_115213.json`
* `data/cleaned/exclusions_home_app_training_bulb_only_20261012_123319.json`
* `data/cleaned/exclusions_pzem_training_data_20261015_160424.json`

