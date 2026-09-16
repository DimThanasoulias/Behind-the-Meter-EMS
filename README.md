# Greek Commercial Behind-the-Meter Energy Management System (EMS)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![PlatformIO ESP32](https://img.shields.io/badge/PlatformIO-ESP32-orange.svg)](https://platformio.org/)
[![Regulatory Standard](https://img.shields.io/badge/Law-5068%2F2023-brightgreen.svg)](https://ypen.gov.gr)
[![Safety Standard](https://img.shields.io/badge/Standard-ELOT%2060364-red.svg)](https://www.elot.gr)
[![Tests: 438 Passed](https://img.shields.io/badge/tests-438%20passed%20(100%25)-success.svg)](tests/)

An end-to-end Behind-the-Meter Energy Management System (EMS) engineered for **Greek commercial facilities** (artisanal bakeries, cold storage logistics, boutique hotels). The system ingests 3-phase electrical power telemetry from ESP32 microcontrollers sampling split-core current transformers (SCT-013), calculates real-time electricity costs according to Greek commercial tariff schemes (**Γ21, Γ22, Γ23, Green, Yellow, Dynamic**), ingests live energy market prices from **RAE** and **HEnEx**, delivers proactive cost-saving alerts via **Telegram & Viber**, and provides a real-time **Web Dashboard** at `/dashboard`.

---

## Documentation Index

| Guide | Document Link | Description |
|---|---|---|
| **Hardware Schematics & Wiring** | [`docs/wiring_schematic.md`](docs/wiring_schematic.md) | SCT-013 CT clamp connections, burden resistor calculation ($18\,\Omega$), ADC1 pinout, virtual ground, and ELOT 60364 safety standards. |
| **Hardware Bill of Materials (BOM)** | [`docs/hardware_bom.md`](docs/hardware_bom.md) | Sub-€50 component list, part numbers, suppliers, PCB layout, and DIN-rail enclosure recommendations. |
| **Greek Commercial Electricity Tariffs** | [`docs/greek_tariffs_guide.md`](docs/greek_tariffs_guide.md) | Detailed analysis of contracts Γ21, Γ22, Γ23, Law 5068/2023 Green tariff formula, DEDDIE peak schedules, and power factor penalties. |
| **REST API Reference** | [`docs/api_reference.md`](docs/api_reference.md) | FastAPI endpoint documentation, JSON request/response schemas, market feeds, Viber webhook, and dashboard endpoints. |
| **Telegram & Viber Bot Guide** | [`docs/telegram_bot_guide.md`](docs/telegram_bot_guide.md) | BotFather configuration, Viber bot tokens, webhook routing, anti-spam throttling, and Greek interactive commands. |
| **Production Deployment Guide** | [`docs/deployment_guide.md`](docs/deployment_guide.md) | Systemd unit configuration, environment variables, PlatformIO ESP32 firmware flashing, and operations runbook. |

---

## 1. System Architecture

```
+-------------------------------------------------------------------------------+
|                             Physical Metering Point                           |
|  3-Phase Mains (L1, L2, L3) ---> SCT-013-000 CT Clamps (2000:1)               |
|                                         |                                     |
|                                         v (Burden Resistors: 18Ω / 22Ω)       |
|                                   DC Bias (1.65V Virtual Midpoint)            |
|                                         v                                     |
|                             ESP32 ADC1 (GPIO 34, 35, 32)                      |
|                             *ADC2 is reserved for Wi-Fi RF*                   |
+-----------------------------------------+-------------------------------------+
                                          | Wi-Fi (HTTPS REST / MQTT)
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
|  | (|P_tot - ΣP_i| <= 0.05 kW) |     | - High-throughput indexed storage   |  |
|  +-----------------------------+     +-------------------------------------+  |
|          |                                              ^                     |
|          v                                              |                     |
|  +------------------------------------------------------+------------------+  |
|  | Greek Tariff & Real-Time Cost Engine                                    |  |
|  | - Contracts: Γ21 (Single), Γ22 (Dual-Rate), Γ23 (Medium Voltage)        |  |
|  | - Colors: Green (Law 5068/2023 MD Formula), Yellow, Dynamic (DAM Spot)   |  |
|  | - Live Market Feeds: RAE Monthly Green Tariffs & HEnEx 24h DAM Curve    |  |
|  | - Regulated Charges: DEDDIE, ADMIE, ETMEAR, YKO, EFK, DETE, 6% VAT      |  |
|  | - Penalties: Contracted Capacity Excess, Low cos φ (< 0.85)             |  |
|  | - Real-Time Metrics: €/h, Daily Spend (€), Projected Peak Penalty (€)   |  |
|  +-------------------------------------------------------------------------+  |
|          |                                                                    |
|          +------------------------------------+                               |
|          |                                    |                               |
|          v                                    v                               |
|  +---------------------------------+  +------------------------------------+  |
|  | Unified Alerting Subsystem      |  | Interactive Web Dashboard UI       |  |
|  | - 30-min Cooldown & Hysteresis  |  | - Route: GET /dashboard            |  |
|  | - Multi-Channel Router:         |  | - Real-time 3-Phase Gauges         |  |
|  |   * Telegram Bot Client         |  | - DEDDIE Zone & Cost (€/h, Today)  |  |
|  |   * Viber Bot Client & Webhook  |  | - 24h Load vs Threshold Chart.js   |  |
|  |   * Channel: Telegram/Viber/Both|  | - In-Browser Threshold Management  |  |
|  +---------------------------------+  +------------------------------------+  |
+-------------------------------------------------------------------------------+
```

---

## 2. Feature Inventory (F01–F33)

| # | Feature | Subsystem | Description |
|---|---|---|---|
| **F01** | ESP32 Analog Sampling & ADC1 Pinout | Firmware | Non-invasive CT sampling using ADC1 (GPIO 34, 35, 32), DC bias (1.65V), avoiding Wi-Fi ADC2 conflict |
| **F02** | SCT-013 Burden Resistor Derivation | Firmware | Exact derivation for SCT-013-000 ($18\,\Omega$ for 3.3V, $22\,\Omega$ for 5V) and SCT-013-030 internal burden |
| **F03** | 3-Phase Electrical Power Calculations | Firmware | Computation of True RMS current, active power ($P$), apparent power ($S$), power factor ($\cos\varphi$) |
| **F04** | Trapezoidal Cumulative Energy Integration | Firmware | Real-time numeric integration of active power into cumulative kWh |
| **F05** | ESP32 Wi-Fi & Reconnection Resilience | Firmware | Automatic exponential backoff reconnection for Wi-Fi and HTTPS/MQTT endpoints |
| **F06** | ESP32 Telemetry Store-and-Forward | Firmware | In-memory ring buffer holding telemetry readings during temporary network dropouts |
| **F07** | PlatformIO Clean Build Configuration | Firmware | Clean compilable `platformio.ini` for `esp32dev` board without warnings/errors |
| **F08** | Greek Tariff Contract Γ21 (LV Commercial) | Tariff Engine | Single-rate commercial tariff modeling for $\le 25\text{ kVA}$ connections |
| **F09** | Greek Tariff Contract Γ22 (Dual Rate) | Tariff Engine | Commercial dual-rate tariff modeling with DEDDIE peak and off-peak windows |
| **F10** | Greek Tariff Contract Γ23 (MV Commercial) | Tariff Engine | Medium voltage commercial structure modeling ($> 250\text{ kVA}$) |
| **F11** | Green Tariff Fluctuation Mechanism | Tariff Engine | Official Law 5068/2023 / MD ΥΠΕΝ formula with TEA, $\alpha$, $L_u$, $L_l$, $\beta$ parameters |
| **F12** | Yellow & Dynamic Hourly Spot Tariff | Tariff Engine | Day-Ahead Market (DAM) hourly spot price indexing with supplier margins |
| **F13** | Regulated Charges Modeling | Tariff Engine | DEDDIE distribution, ADMIE transmission, ETMEAR, YKO, EFK, DETE, and 6% VAT |
| **F14** | Capacity Excess & Power Factor Penalties | Tariff Engine | Penalties for exceeding contracted kVA and $\cos\varphi < 0.85$ distribution multiplier |
| **F15** | Real-Time Running Cost (€/h) & Daily Spend | Tariff Engine | Instantaneous €/h calculation, daily spend accumulator, and baseline delta |
| **F16** | Projected Peak-Hour Surcharge Calculation | Tariff Engine | Mathematical projection of excess cost during active peak tariff windows |
| **F17** | Backend Telemetry Ingestion API | Backend | FastAPI REST endpoint (`POST /api/v1/telemetry`) with Pydantic v2 payload validation |
| **F18** | Electrical Invariant Validation | Backend | Strict backend checks ensuring $\vert P_{tot} - \sum P_i \vert \le 0.05\text{ kW}$ and $\cos\varphi \in [-1, 1]$ |
| **F19** | SQLite Time-Series Storage | Backend | High-throughput SQLite storage with WAL mode, facility indexing, and query APIs |
| **F20** | Facility Status & Cost Endpoints | Backend | `GET /api/v1/facilities/{id}/status`, `/cost-today`, `/tariff` for dashboards and bot queries |
| **F21** | Proactive Peak Breach Alert Generation | Alerting | Automated triggering of proactive alerts when load breaches kW threshold during peak rates |
| **F22** | Greek Alert Notification Templates | Alerting | Greek messages with kW, peak window, estimated € penalty, and tailored curtailment advice |
| **F23** | Alert Throttling, Cooldown & Hysteresis | Alerting | 3-sample debounce, 30-min cooldown, $\ge 25\%$ escalation jump, 10% release hysteresis |
| **F24** | Telegram Bot Greek Command Handlers | Alerting | Interactive commands (`/start`, `/status`, `/cost_today`, `/tariff`, `/settings`, `/help`) |
| **F25** | Dual Telegram Client Architecture | Alerting | `MockTelegramClient` for deterministic offline testing + `LiveTelegramClient` for production |
| **F26** | Commercial Telemetry Simulator CLI | Simulator | Parametric simulation for Commercial Bakery, Cold Storage, and Boutique Hotel |
| **F27** | Simulator Fast-Forward & Breach Triggering | Simulator | Configurable time-compression (`--speed`), Gaussian noise (`--noise`), and breach injection |
| **F28** | Hardware Wiring Schematics & Safety Guide | Hardware | Complete circuit diagrams, SCT-013 CT clamp connections, burden resistor sizing, and safety rules |
| **F29** | System Deployment & Operation Guide | Deployment | Production setup guide with PlatformIO, systemd, `.env`, Telegram bot setup, and runbook |
| **F30** | End-to-End Automated Integration Test Suite | Testing | Standalone automated script executing under 30s, verifying full pipeline from simulator to alert |
| **F31** | Live Greek Energy Market Price Ingestion | Market Feeds | Scraping of monthly RAE Green tariffs & 24h HEnEx DAM spot prices with 4-tier caching |
| **F32** | Unified Multi-Channel Alerting & Viber Bot | Alerting | Multi-channel dispatching (`telegram`, `viber`, `both`), `MockViberClient`, live Viber webhook, HMAC check |
| **F33** | Interactive Real-Time Web Dashboard | Dashboard UI | Responsive Single-Page UI at `/dashboard` with 3-phase live metrics, DEDDIE badges, 24h load curve |

---

## 3. Quickstart Guide

### 3.1 Installation
Clone the repository and install dependencies using Python 3.11+:
```bash
git clone https://github.com/DimThanasoulias/Behind-the-Meter-EMS.git
cd Behind-the-Meter-EMS

# Create virtual environment and install in editable mode
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### 3.2 Run Automated Test Suite (438 Tests)
```bash
pytest -v
```
All 438 tests execute in under 5.0 seconds with 100% pass rate.

### 3.3 Start the FastAPI Backend & Web Dashboard
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser at:
- **Interactive Web Dashboard:** `http://localhost:8000/dashboard`
- **Interactive OpenAPI Documentation:** `http://localhost:8000/docs`

### 3.4 Run Standalone E2E Verification (< 30 Seconds)
```bash
# Default (Commercial Bakery)
python scripts/run_e2e_verification.py --profile bakery

# Cold Storage Facility
python scripts/run_e2e_verification.py --profile cold_storage

# Boutique Hotel (accepts 'hotel' or 'boutique_hotel')
python scripts/run_e2e_verification.py --profile hotel
```
Validates the entire end-to-end telemetry, tariff, debounce, cooldown, hysteresis, and multi-channel notification pipeline dynamically for each commercial facility profile in **< 1.0 second**.

### 3.5 Run the Commercial Telemetry Simulator
Stream 24 hours of compressed Bakery commercial load with breach injection:
```bash
python -m simulator.cli --profile bakery --speed 60x --url http://localhost:8000/api/v1/telemetry
```

---

## 4. Hardware Wiring & Sensor Interfacing Summary

*For complete circuit diagrams, mathematical derivations, and safety rules, see [`docs/wiring_schematic.md`](docs/wiring_schematic.md).*

### 4.1 SCT-013-000 Burden Resistor Sizing
- **Turns Ratio:** $2000:1$ ($100\text{ A RMS primary} \implies 50\text{ mA RMS secondary} \implies 70.71\text{ mA peak}$).
- **3.3V ESP32 ADC ($18\,\Omega$ 1% Metal Film):**
  $$V_{peak} = 0.07071\text{ A} \times 18\,\Omega = 1.273\text{ V} \implies V_{pp} = 2.546\text{ V}$$
  Biased at $1.65\text{ V}$, signal spans $[0.377\text{ V}, 2.923\text{ V}]$, remaining safely within the ESP32's linear range ($0.15\text{ V} - 3.10\text{ V}$).
  **Calibration factor:** $K_I = 2000 / 18 = 111.111\text{ A/V} = 0.11111\text{ A/mV}$.
- **5.0V External ADC ($22\,\Omega$ 1% Metal Film):**
  $$V_{peak} = 0.07071\text{ A} \times 22\,\Omega = 1.556\text{ V} \implies V_{pp} = 3.111\text{ V}$$
  **Calibration factor:** $K_I = 2000 / 22 = 90.909\text{ A/V} = 0.09091\text{ A/mV}$.

### 4.2 ESP32 Pin Allocation (ADC1 Exclusively)
- **Phase L1:** GPIO 34 (`ADC1_CH6`)
- **Phase L2:** GPIO 35 (`ADC1_CH7`)
- **Phase L3:** GPIO 32 (`ADC1_CH4`)
- **ADC2 Restriction:** The ESP32 Wi-Fi RF driver locks ADC2. Sampling ADC2 pins causes Wi-Fi disconnects and measurement errors.

### 4.3 Open CT Hazard & Electrical Safety (ELOT 60364)
- When a CT secondary is open-circuit ($Z \to \infty$), the core saturates and induces lethal voltage spikes ($> 1000\text{ V}$).
- SCT-013-000 includes internal bidirectional TVS clamp diodes ($\pm 8.2\text{V} - \pm 9.1\text{V}$) for transient protection.
- Always clamp around **single phase conductors only** (never clamp Phase + Neutral together).

---

## 5. Software Deployment & Production Operations

*For systemd unit files, `.env` templates, and PlatformIO flashing guides, see [`docs/deployment_guide.md`](docs/deployment_guide.md).*

### 5.1 Environment Configuration (`.env`)
```ini
ENVIRONMENT=production
DEBUG=false
SQLITE_DB_PATH=/var/lib/ems/ems_timeseries.db
TELEGRAM_BOT_TOKEN=7123456789:AAFlkjw98234-example-token
TELEGRAM_DEFAULT_CHAT_ID=999111222
ALERT_COOLDOWN_SECONDS=1800
ALERT_HYSTERESIS_FACTOR=0.90
ALERT_DEBOUNCE_SAMPLES=3
TIMEZONE=Europe/Athens
DEFAULT_CONTRACT_TYPE=Γ22
DEFAULT_TARIFF_COLOR=green
```

### 5.2 Production Service (systemd)
Run as a background systemd daemon (`/etc/systemd/system/ems-backend.service`) with automatic restart and logging.

---

## 6. Greek Electricity Tariff Engine

Models Greek commercial electricity contracts with exact mathematical fidelity:

### 6.1 Commercial Contract Schemes
- **Γ21 (Commercial Single-Rate LV):** Standard commercial connections $\le 25\text{ kVA}$. Uniform 24-hour rate.
- **Γ22 (Commercial Dual-Rate LV):** Commercial connections $> 25\text{ kVA}$ with DEDDIE time-of-use schedules:
  - **Summer Peak (May 1 – Oct 31):** `14:00 – 17:00` (Mon–Fri).
  - **Winter Peak (Nov 1 – Apr 30):** `17:00 – 21:00` (Mon–Fri).
  - **Off-Peak / Night Window:** `23:00 – 07:00` (Summer) / `02:00 – 08:00` & `15:00 – 17:00` (Winter).
  - *Weekends and official Greek holidays are exempt from peak rates.*
- **Γ23 (Commercial Medium Voltage):** MV commercial enterprises ($> 250\text{ kVA}$) with tri-rate time-of-use pricing.

### 6.2 Green Tariff Fluctuation Mechanism (Law 5068/2023)
The official Greek Ministerial Decision (ΥΠΕΝ) Fluctuation Mechanism ($MD$):

$$MD = \begin{cases} 
\alpha \times (TEA_{m-1} - L_u), & \text{if } TEA_{m-1} > L_u \\
0, & \text{if } L_l \le TEA_{m-1} \le L_u \\
\alpha \times (TEA_{m-1} - L_l), & \text{if } TEA_{m-1} < L_l 
\end{cases}$$

Final Retail Supply Rate:

$$R_{\text{final}} = \max\Big(0.00,\; B + MD \times (1 - L_{\text{loss}}) + \beta\Big)$$

*(where $L_{\text{loss}}$ is the grid distribution loss factor, typically $13.5\%$)*

### 6.3 Yellow & Dynamic Hourly Spot Pricing
- **Yellow (Indexed):** Indexed directly to wholesale clearing with fixed monthly retail margins.
- **Dynamic / Orange (Spot DAM):** Hourly clearing rates from the Hellenic Energy Exchange (HEnEx) with 13.5% distribution loss factor.

### 6.4 Regulated Charges & Greek Levies
Includes exact DEDDIE distribution charges, ADMIE transmission charges, ETMEAR renewable energy surcharge, YKO public service levy, EFK excise tax, DETE $5‰$ duty, and **6% Greek electricity VAT**.

### 6.5 Penalties & Invariant Enforcement
- **Capacity Excess:** Surcharge incurred when instantaneous apparent power exceeds contracted kVA.
- **Power Factor Penalty Multiplier:** Applied to DEDDIE distribution charges when $\cos\varphi < 0.85$:
  $$F_{PF} = \frac{0.85}{\cos\varphi}$$

---

## 7. Telegram Alert Bot & Greek Command Guide

### 7.1 Proactive Alert State Machine
- **3-Sample Debounce Filter:** 3 consecutive telemetry readings above threshold within a peak window are required before triggering an alert (prevents false alarms from motor inrush currents).
- **30-Minute Cooldown Period:** Suppresses duplicate notifications while a breach persists.
- **$\ge 25\%$ Sudden Escalation Bypass:** If load jumps $\ge 25\%$ above the previous alerted load, the cooldown is broken immediately to deliver an Escalation alert (`ΚΛΙΜΑΚΩΣΗ ΥΠΕΡΒΑΣΗΣ`).
- **10% Release Hysteresis Recovery:** The facility state clears back to normal only when load drops $\le 0.90 \times \text{threshold}$, dispatching a Normalization recovery alert (`ΟΜΑΛΟΠΟΙΗΣΗ ΚΑΤΑΝΑΛΩΣΗΣ`).

### 7.2 Tailored Curtailment Guidance
- **Commercial Bakery:** `"Πρόταση: Μεταφέρετε το ψήσιμο παρτίδας στη ζώνη μειωμένης χρέωσης ή σβήστε προσωρινά 1 φούρνο."`
- **Cold Storage Logistics:** `"Πρόταση: Κλείστε άμεσα τις πόρτες φορτοεκφόρτωσης και καθυστερήστε τον κύκλο απόψυξης."`
- **Boutique Hotel:** `"Πρόταση: Αυξήστε τη θερμοκρασία κλιματισμού VRV κατά 1.5°C και αναστείλετε τα πλυντήρια."`

### 7.3 Interactive Bot Commands

| Command | Description | Example Output |
|---|---|---|
| `/status` | 3-phase voltages, currents, active kW, kVA, cos φ, €/h running cost, active zone | `Συνολική Ισχύς: 17.90 kW \| Τρέχον Κόστος: 4.39 €/h \| Ζώνη Αιχμής` |
| `/cost_today` | Today's accumulated kWh, total spend (€), peak surcharge (€), average rate | `Ενέργεια: 240.5 kWh \| Κόστος: 48.60 € \| Μέση Τιμή: 0.202 €/kWh` |
| `/tariff` | Contract type, color, contracted kVA, peak threshold kW, DEDDIE schedule | `Τύπος: Γ22 \| Χρώμα: Πράσινο \| Συμφωνημένη: 35 kVA \| Όριο: 22.0 kW` |
| `/settings` | Thresholds, cooldown minutes, 90% hysteresis limit, debounce samples, Chat ID | `Όριο: 22.0 kW \| Cooldown: 30 λεπτά \| Υστέρηση: 90% (19.8 kW)` |
| `/help` | Complete command guide in Greek | Comprehensive command directory |
| `/start` | System overview and introductory message | Welcome message and available command list |

---

## 8. Commercial Telemetry Simulator CLI

The simulator emulates realistic commercial SMB load profiles without requiring physical hardware:

```bash
python -m simulator.cli [OPTIONS]
```

### Available Options:
- `--profile`: `bakery`, `cold_storage`, or `boutique_hotel` (default: `bakery`).
- `--speed`: Simulation acceleration factor: `1x`, `60x`, `3600x` (default: `60x`).
- `--duration-hours`: Duration of simulation run (default: `24.0`).
- `--interval-seconds`: Measurement cadence (default: `10.0`).
- `--url`: Backend REST endpoint URL (`POST /api/v1/telemetry`).
- `--trigger-breach`: Force instantaneous high-load peak breach.
- `--noise`: Gaussian noise standard deviation in kW (default: `0.3`).
- `--dry-run`: Output formatted readings to stdout without network dispatch.

---

## 9. Verification & Automated Testing

### 9.1 Complete Test Suite (438 Unit, Integration & Tiered E2E Tests)
```bash
pytest -v
```

### 9.2 Standalone End-to-End Verification Script
```bash
python scripts/run_e2e_verification.py --profile bakery
python scripts/run_e2e_verification.py --profile cold_storage
python scripts/run_e2e_verification.py --profile hotel
```
Validates all 9 critical acceptance checks dynamically across commercial SMB profiles in under 1 second.

---

## 10. Regulatory Compliance & Electrical Safety

- **ELOT 60364 / HD 384:** Electrical installations of buildings. Guarantees isolation between low-voltage signal wiring and 400V mains busbars.
- **Law 5068/2023 & MD ΥΠΕΝ:** Greek retail electricity market reorganization establishing Green, Yellow, and Dynamic retail tariffs.
- **DEDDIE & ADMIE Grid Codes:** Compliant with distribution network connection terms, contracted kVA thresholds, and low power factor surcharge schedules ($\cos\varphi < 0.85$).
