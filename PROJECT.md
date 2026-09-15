# Project: Greek Commercial Behind-the-Meter Energy Management System (EMS)

## Architecture
The Behind-the-Meter Energy Management System (EMS) is a production-grade, modular system engineered for Greek commercial enterprises (bakeries, cold storage facilities, boutique hotels). It ingests real-time 3-phase power telemetry from ESP32 microcontrollers monitoring split-core current transformers (SCT-013), calculates electricity costs according to official Greek commercial tariff schemes (Γ21, Γ22, Γ23, Green, Yellow, Dynamic), and delivers proactive Greek-language cost-saving alerts via Telegram before costly peak-hour demand surcharges accumulate.

```
+-------------------------------------------------------------------------------+
|                             Physical Metering Point                           |
|  3-Phase Mains (L1, L2, L3) ---> SCT-013-000 CT Clamps (2000:1)               |
|                                         |                                     |
|                                         v (Burden Resistor 18Ω / 22Ω)         |
|                                   DC Bias (1.65V)                             |
|                                         v                                     |
|                             ESP32 ADC1 (GPIO 34, 35, 32)                      |
+-----------------------------------------+-------------------------------------+
                                          | Wi-Fi (REST / MQTT)
                                          v
+-------------------------------------------------------------------------------+
|                       Backend Telemetry Ingestion Service                     |
|                                 (FastAPI)                                     |
|                                                                               |
|  POST /api/v1/telemetry <---+ [Commercial Telemetry Simulator CLI]             |
|          |                  | (Bakery, Cold Storage, Boutique Hotel)          |
|          v                                                                    |
|  +-----------------------------+     +-------------------------------------+  |
|  | Multi-Phase Invariant Check |     | SQLite Time-Series Store (WAL Mode) |  |
|  +-----------------------------+     +-------------------------------------+  |
|          |                                              ^                     |
|          v                                              |                     |
|  +-------------------------------------------------------------------------+  |
|  | Greek Tariff & Real-Time Cost Engine                                    |  |
|  | - Contracts: Γ21, Γ22, Γ23 (Low / Medium Voltage Commercial)            |  |
|  | - Colors: Green (MD Fluctuation Formula), Yellow, Dynamic (HEnEx DAM)   |  |
|  | - Regulated Fees: DEDDIE, ADMIE, ETMEAR, YKO, EFK, DETE, 6% VAT         |  |
|  | - Penalties: Contracted Capacity Excess, Low cos φ (< 0.85)             |  |
|  | - Real-Time Metrics: €/h, Daily Spend (€), Projected Peak Penalty (€)   |  |
|  +-------------------------------------------------------------------------+  |
|          |                                                                    |
|          v                                                                    |
|  +-------------------------------------------------------------------------+  |
|  | Alert Dispatcher & Throttling Engine                                    |  |
|  | - State Machine: IDLE -> TRIGGERED -> COOLDOWN -> CLEARED              |  |
|  | - 30-minute Cooldown, 10% Hysteresis, 3-sample Debounce Filter         |  |
|  +-------------------------------------------------------------------------+  |
|          |                                                                    |
|          v                                                                    |
|  +-------------------------------------------------------------------------+  |
|  | Telegram Alert Bot Service                                              |  |
|  | - Greek Notification Templates (Peak Breach, Pre-Warning, Cleared)      |  |
|  | - Greek Interactive Commands: /status, /cost_today, /tariff, /settings  |  |
|  | - Dual Mode Client: LiveTelegramClient / MockTelegramClient             |  |
|  +-------------------------------------------------------------------------+  |
+-------------------------------------------------------------------------------+
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | ESP32 Analog Sampling & ADC1 Pinout | Non-invasive CT sampling using ADC1 (GPIO 34, 35, 32), DC bias (1.65V), avoiding Wi-Fi ADC2 conflict | M4 | ORIGINAL_REQUEST §R1 |
| F02 | SCT-013 Burden Resistor Derivation | Exact calculation for SCT-013-000 (18Ω / 22Ω) and SCT-013-030 (internal burden) | M4 | ORIGINAL_REQUEST §R1 |
| F03 | 3-Phase Electrical Power Calculations | Computation of True RMS current, active power (kW), apparent power (kVA), power factor (cos φ) | M4 | ORIGINAL_REQUEST §R1 |
| F04 | Trapezoidal Cumulative Energy Integration | Real-time numeric integration of active power into cumulative kWh | M4 | ORIGINAL_REQUEST §R1 |
| F05 | ESP32 Wi-Fi & Reconnection Resilience | Automatic exponential backoff reconnection for Wi-Fi and HTTP/MQTT endpoints | M4 | ORIGINAL_REQUEST §R1 |
| F06 | ESP32 Telemetry Store-and-Forward | In-memory ring buffer holding telemetry readings during temporary network dropouts | M4 | ORIGINAL_REQUEST §R1 |
| F07 | PlatformIO Clean Build Configuration | Clean compilable platformio.ini for esp32dev board without warnings/errors | M4 | ORIGINAL_REQUEST §R1 |
| F08 | Greek Tariff Contract Γ21 (LV Commercial) | Single-rate commercial tariff modeling for <= 25 kVA connections | M2 | ORIGINAL_REQUEST §R2 |
| F09 | Greek Tariff Contract Γ22 (Dual Rate) | Commercial dual-rate tariff modeling with DEDDIE peak and off-peak windows | M2 | ORIGINAL_REQUEST §R2 |
| F10 | Greek Tariff Contract Γ23 (MV Commercial) | Medium voltage commercial structure modeling | M2 | ORIGINAL_REQUEST §R2 |
| F11 | Green Tariff Fluctuation Mechanism | Official Law 5068/2023 / MD ΥΠΕΝ formula with TEA, alpha, Lu, Ll, beta parameters | M2 | ORIGINAL_REQUEST §R2 |
| F12 | Yellow & Dynamic Hourly Spot Tariff | Day-Ahead Market (DAM) hourly spot price indexing with supplier margins | M2 | ORIGINAL_REQUEST §R2 |
| F13 | Regulated Charges Modeling | DEDDIE distribution, ADMIE transmission, ETMEAR, YKO, EFK, DETE, and 6% VAT | M2 | ORIGINAL_REQUEST §R2 |
| F14 | Capacity Excess & Power Factor Penalties | Penalties for exceeding contracted kVA and cos φ < 0.85 distribution multiplier | M2 | ORIGINAL_REQUEST §R2 |
| F15 | Real-Time Running Cost (€/h) & Daily Spend | Instantaneous €/h calculation, daily spend accumulator, and baseline delta | M2 | ORIGINAL_REQUEST §R2 |
| F16 | Projected Peak-Hour Surcharge Calculation | Mathematical projection of excess cost during active peak tariff windows | M2 | ORIGINAL_REQUEST §R2 |
| F17 | Backend Telemetry Ingestion API | FastAPI REST endpoint (POST /api/v1/telemetry) with Pydantic v2 payload validation | M3 | ORIGINAL_REQUEST §R4 |
| F18 | Electrical Invariant Validation | Strict backend checks ensuring |P_tot - sum(P_i)| <= 0.05 kW and cos φ in [-1, 1] | M3 | ORIGINAL_REQUEST §R4 |
| F19 | SQLite Time-Series Storage | High-throughput SQLite storage with WAL mode, facility indexing, and query APIs | M3 | ORIGINAL_REQUEST §R4 |
| F20 | Facility Status & Cost Endpoints | GET /api/v1/facilities/{id}/status, /cost-today, /tariff for dashboards/bot | M3 | ORIGINAL_REQUEST §R4 |
| F21 | Proactive Peak Breach Alert Generation | Automated triggering of proactive alerts when load breaches kW threshold during peak rates | M5 | ORIGINAL_REQUEST §R3 |
| F22 | Greek Alert Notification Templates | Greek formatted messages with current kW, peak window, estimated € penalty, and curtailment tips | M5 | ORIGINAL_REQUEST §R3 |
| F23 | Alert Throttling, Cooldown & Hysteresis | 3-sample debounce, 30-min cooldown per category, 10% release hysteresis to prevent spam | M5 | ORIGINAL_REQUEST §R3 |
| F24 | Telegram Bot Greek Command Handlers | Interactive commands (/start, /status, /cost_today, /tariff, /settings, /alerts, /help) | M5 | ORIGINAL_REQUEST §R3 |
| F25 | Dual Telegram Client Architecture | MockTelegramClient for 100% offline, deterministic tests + LiveTelegramClient for production | M5 | ORIGINAL_REQUEST §R3 |
| F26 | Commercial Telemetry Simulator CLI | Realistic simulation CLI for Commercial Bakery, Cold Storage, and Boutique Hotel profiles | M6 | ORIGINAL_REQUEST §R4 |
| F27 | Simulator Fast-Forward & Breach Triggering | Configurable time-compression (--speed), Gaussian noise (--noise), and breach injection | M6 | ORIGINAL_REQUEST §R4 |
| F28 | Hardware Wiring Schematics & Safety Guide | Complete circuit diagrams, SCT-013 CT clamp connections, burden resistor sizing, and safety rules | M7 | Acceptance Criteria |
| F29 | System Deployment & Operation Guide | Comprehensive README.md with hardware schematics, environment configuration, and runbook | M7 | Acceptance Criteria |
| F30 | End-to-End Automated Integration Test Suite | Standalone automated script executing under 30s, verifying full pipeline from simulator to alert | M7 | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Foundation & Testing Infrastructure | Project structure, Pydantic schemas, MockTelegramClient, database fixtures, pytest setup | None | PLANNED |
| M2 | Greek Tariff & Real-Time Cost Engine | Pure deterministic tariff engine (Γ21, Γ22, Γ23, Green, Yellow, Dynamic, Regulated, Penalties) | M1 | PLANNED |
| M3 | Backend Telemetry Ingestion & Storage | FastAPI REST ingestion, electrical validation, SQLite WAL time-series store, status endpoints | M1, M2 | PLANNED |
| M4 | ESP32 3-Phase Firmware & Telemetry Architecture | C++/Arduino firmware for PlatformIO, SCT-013 ADC1 sampling, power math, Wi-Fi/REST buffer | M1 | PLANNED |
| M5 | Proactive Telegram Alert Bot & Dispatcher | Throttled alert state machine, Greek alert templates, interactive Greek command handlers | M1, M2, M3 | PLANNED |
| M6 | Commercial Telemetry Simulator CLI | Parametric load generator for Bakery, Cold Storage, Hotel with CLI breach injection | M1, M3 | PLANNED |
| M7 | Full System E2E Integration, Hardening & Docs | 100% E2E test pass, adversarial test coverage, README.md with wiring diagrams & deployment guide | M1-M6 | PLANNED |

## Interface Contracts
### Firmware / Simulator ↔ Backend Ingestion
- Endpoint: `POST /api/v1/telemetry`
- Content-Type: `application/json`
- Payload Schema (`TelemetryPayload`):
  ```json
  {
    "device_id": "esp32-ems-001",
    "facility_id": "bakery-central-athens",
    "timestamp": "2026-09-14T15:30:00Z",
    "phases": {
      "L1": {"voltage_v": 230.2, "current_a": 26.4, "active_power_kw": 5.95, "apparent_power_kva": 6.08, "power_factor": 0.98},
      "L2": {"voltage_v": 229.8, "current_a": 25.8, "active_power_kw": 5.82, "apparent_power_kva": 5.93, "power_factor": 0.98},
      "L3": {"voltage_v": 231.0, "current_a": 27.1, "active_power_kw": 6.13, "apparent_power_kva": 6.26, "power_factor": 0.98}
    },
    "total_active_power_kw": 17.90,
    "total_apparent_power_kva": 18.27,
    "system_power_factor": 0.98,
    "cumulative_energy_kwh": 142.50,
    "grid_frequency_hz": 50.01,
    "wifi_rssi_dbm": -62
  }
  ```
- Validation Invariant: `|total_active_power_kw - sum(phases[Li].active_power_kw)| <= 0.05`

### Backend ↔ Tariff Engine
- Pure function: `calculate_realtime_cost(power_kw, energy_kwh_delta, timestamp, tariff_profile, contracted_kva)`
- Output: `CostCalculationResult(current_rate_eur_per_kwh, running_cost_eur_per_h, incremental_cost_eur, is_peak_window, is_excess_breach, excess_power_kw, projected_excess_penalty_eur)`

### Backend / Dispatcher ↔ Telegram Bot
- Alert Trigger: `dispatch_alert(alert_event: AlertEvent) -> bool`
- Bot Mock: `MockTelegramClient` records sent messages in an in-memory queue with inspection API `get_sent_messages()` and `clear()`.

## Code Layout
```
e:\project1\
├── firmware/
│   ├── platformio.ini                  # PlatformIO configuration for esp32dev board
│   ├── src/
│   │   ├── main.cpp                    # ESP32 main setup and sampling loop
│   │   ├── ct_sampler.h / .cpp         # ADC1 3-phase sampling and SCT-013 calibration
│   │   ├── power_calc.h / .cpp         # RMS current, active/apparent power, cos φ, kWh
│   │   ├── telemetry_client.h / .cpp   # Wi-Fi management, JSON payload, REST/MQTT dispatch
│   │   └── ring_buffer.h               # Offline store-and-forward telemetry buffer
├── backend/
│   ├── __init__.py
│   ├── main.py                         # FastAPI application entrypoint
│   ├── config.py                       # Application settings & environment variables
│   ├── models/
│   │   ├── __init__.py
│   │   ├── telemetry.py                # Pydantic v2 schemas for telemetry
│   │   └── alert.py                    # Alert schemas and event structures
│   ├── database/
│   │   ├── __init__.py
│   │   └── sqlite_store.py             # SQLite WAL time-series store and queries
│   └── routes/
│       ├── __init__.py
│       ├── telemetry.py                # POST /api/v1/telemetry endpoint
│       └── facilities.py               # GET facility status and cost endpoints
├── tariff_engine/
│   ├── __init__.py
│   ├── contracts.py                    # Γ21, Γ22, Γ23 contract definitions
│   ├── green_tariff.py                 # Law 5068/2023 Fluctuation Mechanism (MD formula)
│   ├── yellow_dynamic.py               # Day-Ahead Market (DAM) hourly spot rates
│   ├── regulated_charges.py            # DEDDIE, ADMIE, ETMEAR, YKO, EFK, VAT
│   ├── penalties.py                    # Capacity excess & power factor penalties
│   └── cost_calculator.py              # Real-time running cost & excess projector
├── bot/
│   ├── __init__.py
│   ├── dispatcher.py                   # Throttling, cooldown, hysteresis state machine
│   ├── templates_el.py                 # Localized Greek alert & command templates
│   ├── command_handlers.py             # /status, /cost_today, /tariff, /settings
│   └── telegram_client.py              # ITelegramClient, LiveTelegramClient, MockTelegramClient
├── simulator/
│   ├── __init__.py
│   ├── cli.py                          # Standalone CLI simulator
│   ├── profiles/
│   │   ├── __init__.py
│   │   ├── bakery.py                   # Commercial Bakery load profile
│   │   ├── cold_storage.py             # Cold Storage refrigeration compressor cycles
│   │   └── boutique_hotel.py           # Boutique Hotel load profile
│   └── generator.py                    # Load generator with noise and breach injection
├── tests/
│   ├── conftest.py                     # Shared fixtures (mock client, test DB, sample data)
│   ├── unit/
│   │   ├── test_tariff_engine.py       # Tariff calculations, penalties, Green formula
│   │   ├── test_telemetry_models.py    # Schema validation & invariant enforcement
│   │   ├── test_alert_dispatcher.py    # Throttling, cooldown, hysteresis logic
│   │   ├── test_simulator_profiles.py  # Bakery, cold storage, hotel load curves
│   │   └── test_firmware_math.py       # True RMS, burden resistor, power factor math
│   ├── integration/
│   │   ├── test_ingestion_api.py       # API endpoints, SQLite persistence
│   │   └── test_bot_commands.py        # Greek command formatting and response
│   └── e2e/
│       ├── test_full_pipeline_e2e.py   # Full pipeline simulation to Telegram alert (<3.5s)
│       └── test_tiers/                 # Opaque-box requirement-driven test suite
├── scripts/
│   └── run_e2e_verification.py         # Dedicated standalone verification script
├── docs/
│   ├── wiring_schematic.md             # SCT-013 wiring diagrams, burden resistors
│   └── deployment_guide.md             # Production setup and configuration
├── ORIGINAL_REQUEST.md                 # Authoritative requirements
└── README.md                           # Comprehensive documentation & setup guide
```
