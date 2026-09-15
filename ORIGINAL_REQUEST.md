# Original User Request

## 2026-09-14T15:22:09Z

Build an end-to-end Behind-the-Meter Energy Management System (EMS) tailored for Greek commercial SMBs (bakeries, boutique hotels, cold storage) that ingests 3-phase CT-clamp power telemetry from an ESP32, tracks Greek commercial electricity tariff pricing structures (green, yellow, and hourly spot markets), and delivers proactive, actionable cost-saving alerts directly via a Telegram bot.

Working directory: e:\project1
Integrity mode: development

## Requirements

### R1. ESP32 3-Phase Firmware & Telemetry Architecture
Develop clean, modular ESP32 firmware (C++/Arduino or ESP-IDF) to sample 3-phase currents via non-invasive split-core Current Transformers (CT clamps, e.g., SCT-013 series). Compute active power (kW), apparent power (kVA), power factor (cos φ), and cumulative energy (kWh). The firmware must support Wi-Fi connectivity, MQTT or HTTPS telemetry transmission with reconnection resilience, and configurable sampling intervals.

### R2. Greek Electricity Tariff & Real-Time Cost Engine
Implement a tariff calculation engine modeling Greek commercial electricity contracts (Γ21, Γ22, Γ23):
- Green tariffs (fixed component + monthly formula based on wholesale electricity price / TEA).
- Yellow & dynamic tariffs (indexed directly to wholesale day-ahead market hourly clearing rates).
- Peak-demand surcharge windows and capacity excess penalties.
The engine calculates real-time instantaneous running costs (€/h), daily accumulated spend, and projected excess cost penalties during peak tariff hours.

### R3. Proactive Telegram Alert Bot
Implement an interactive Telegram bot with Greek-language notifications and conversational commands:
- Proactive alerts when power draw exceeds configured kW thresholds during high-tariff windows (e.g. "Προσοχή: Τα ψυγεία καταναλώνουν 18.4 kW σε ζώνη υψηλής χρέωσης (14:00–17:00). Εκτιμώμενη επιπλέον επιβάρυνση σήμερα: €38").
- Instant status query commands (/status, /cost_today, /tariff, /settings).
- Alert throttling / de-duplication so business owners are not spammed.

### R4. Backend Service & Mock Telemetry Simulator
Provide a lightweight backend (FastAPI / Python or Express / Node.js) that exposes:
- Ingestion endpoints for ESP32 telemetry (MQTT or REST).
- A standalone simulation CLI/script that emulates realistic commercial profiles (e.g., a bakery's morning baking peak or a cold room compressor cycle) to allow 100% full-system verification without physical hardware connected.

## Acceptance Criteria

### Sensor Telemetry & Ingestion
- [ ] ESP32 firmware code compiles cleanly with clear pinout mappings and calibration formulas for split-core CT sensors.
- [ ] Backend telemetry endpoint ingests, validates, and stores multi-phase time-series data with timestamping and payload validation.

### Greek Tariff & Cost Engine
- [ ] Accurately computes energy costs based on configurable Greek tariff profiles (hourly rate schedules and peak window definitions).
- [ ] Detects when load exceeds optimal thresholds during high-rate hours and calculates excess euro cost vs off-peak operation.

### Telegram Bot
- [ ] Telegram bot responds to user commands (/status, /cost_today) with formatted metrics and energy summaries in Greek.
- [ ] Bot triggers automatic proactive warning alerts within 30 seconds when simulated load breaches peak-hour cost thresholds.
- [ ] Includes rate-limiting / cool-down logic to avoid notification spam.

### Verification & Automated Testing
- [ ] A dedicated end-to-end integration test script runs automatically, spins up the mock telemetry generator, feeds data into the backend, and validates that alert events and cost calculations are triggered accurately.
- [ ] Comprehensive documentation (README.md) detailing hardware setup (wiring schematics for 3-phase CT clamps, burden resistors, safety) and software deployment instructions.
