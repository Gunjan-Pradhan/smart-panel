# Smart Load Protection Panel

## Project Overview

An AI-based energy management and optimization system designed to monitor electrical loads, detect abnormal operating behaviour, assess load health, and support safer, more efficient energy usage.

## Project Objectives

- Monitor electrical parameters from connected loads.
- Apply deterministic rules for electrical protection.
- Control load isolation through the protection system.
- Detect abnormal energy-consumption patterns using AI.
- Estimate load health from monitored behaviour.
- Provide a dashboard for monitoring and analysis.

## Technology Stack

- **Firmware:** C++ with PlatformIO
- **Microcontroller:** ESP32-S3
- **Electrical monitoring:** PZEM-004T V4
- **Messaging:** MQTT with Mosquitto
- **Backend:** Python and FastAPI
- **Database:** PostgreSQL with TimescaleDB
- **AI/ML:** NumPy, Pandas, and scikit-learn
- **Dashboard:** React with Vite
- **Containerization:** Docker Compose

## Project Structure

- `backend/` — Backend API and application logic
- `dashboard/` — Web dashboard
- `docs/` — Project documentation
- `firmware/` — ESP32 firmware
- `ml/` — AI models and anomaly-detection logic
- `mosquitto/` — MQTT broker configuration
- `simulator/` — Simulated electrical-load data
- `requirements.txt` — Python dependencies

## Safety Principle

AI provides anomaly detection and analytical insights. Deterministic protection rules remain responsible for safety-critical decisions.

## Development Status

Initial development environment configured. Implementation will proceed phase by phase.
