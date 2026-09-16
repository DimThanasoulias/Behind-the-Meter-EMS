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

## 2026-09-15T09:58:54Z

Enhance the Greek Commercial Behind-the-Meter Energy Management System (EMS) in e:\project1 with automated Greek energy market price ingestion (RAE monthly Green tariffs & HEnEx Day-Ahead hourly spot rates), unified dual-channel alerting (adding Viber Bot alongside Telegram), and a responsive real-time Web Dashboard UI for live monitoring and cost analytics.

Working directory: e:\project1
Integrity mode: development

## Requirements

### R1. Live Greek Energy Market & Tariff Ingestion Engine
Implement automated data retrieval and caching for Greek electricity market pricing:
- Automated ingestion/scraping of official monthly Green Tariff announcements from RAE (energycost.gr / RAE pricing feeds) on the 1st of each month.
- Daily retrieval of 24-hour Day-Ahead Market (DAM) hourly clearing prices from the Hellenic Energy Exchange (HEnEx / ENEX / IPTO feeds) with caching and local fallback when offline.
- Dynamic rate feeds directly updating the existing tariff calculation engine (tariff_engine/).

### R2. Unified Multi-Channel Alerting & Viber Bot Integration
Extend the notification subsystem to support both Telegram and Viber:
- A unified notification dispatcher that abstracts the delivery platform (supporting per-facility channel preference: Telegram, Viber, or Both).
- Viber Bot API adapter supporting outgoing proactive alerts, webhook callback handling for interactive commands, and localized Greek alert formatting.
- MockViberClient mirroring MockTelegramClient for 100% offline, deterministic automated testing.

### R3. Interactive Real-Time Web Dashboard (UI)
Build a clean, responsive web dashboard served directly by the FastAPI backend (e.g. at /dashboard):
- Real-time gauge / display of 3-phase active power (kW), voltage, current, and system power factor (cos φ).
- Live tariff indicator showing active time window (DEDDIE Peak / Normal / Reduced), current running cost (€/h), and today's accumulated spend (€).
- Interactive timeline chart displaying daily power draw vs peak surcharge threshold.
- Quick configuration panel allowing business owners to view and adjust threshold kW and alert preferences.

## Acceptance Criteria

### Market Tariff Ingestion
- [ ] Ingestion engine successfully parses and caches RAE monthly rates and 24-hour HEnEx hourly spot price curves.
- [ ] Graceful fallback to cached or default tariff rates if remote market endpoints are unreachable.

### Viber & Multi-Channel Alerting
- [ ] Viber adapter formats and dispatches proactive peak breach, escalation, and normalization alerts matching Greek templates.
- [ ] Facility configuration allows setting notification target to Telegram, Viber, or Both.
- [ ] MockViberClient records sent messages and integrates with existing integration test suites.

### Web Dashboard
- [ ] Dashboard route (/dashboard) renders correctly without build step errors, displaying live facility status and metrics.
- [ ] Dynamic updates reflect simulated or live telemetry within 1 second.
- [ ] Chart correctly renders the 24-hour load curve with clear visual indication of the peak threshold.

### Testing & Regression
- [ ] All existing 333 tests remain 100% passing with zero regressions.
- [ ] New unit and integration tests cover market ingestion, Viber dispatching, and dashboard endpoints.
- [ ] Updated README.md and docs reflecting the new capabilities and configuration options.
