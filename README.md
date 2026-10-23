# NetWatch — Python-Based Network Device Connectivity Monitor

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask 3.0+](https://img.shields.io/badge/flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/tests-80%20passing-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A production-grade, full-stack network monitoring application built for Computer Engineering and Computer Networks (CN) academic projects. **NetWatch** enables continuous reachability monitoring, latency measurement (Round-Trip Time / RTT), uptime/downtime tracking, automated event detection, and real-time visualization across heterogeneous network nodes (routers, servers, workstations, switches, and printers).

---
run link
https://cn-mini-project-h1nj.vercel.app/


## 🌟 Key Features

- **Live ICMP Connectivity Checks**: Safe, platform-adaptive ping execution (Windows, Linux, macOS) with subprocess execution (`shell=False`) avoiding security vulnerabilities.
- **Round-Trip Time (RTT) Latency Metrics**: High-precision parsing of network round-trip time, sub-millisecond detection, min/max/average statistical aggregation.
- **Uptime / Availability Calculation**: Exact percentage-based availability computed over selectable time horizons (1 hour, 24 hours, 7 days, 30 days, or all time).
- **Concurrent Non-Blocking Monitoring**: Background daemon worker pool utilizing `ThreadPoolExecutor` and threading events to probe devices on custom cadence without UI freeze.
- **Automated Event Detection & State Transitions**: Detects `device_offline`, `device_recovered`, and `high_latency` threshold events with unread badges and persistent logs.
- **Manual "Ping Now" Diagnostics**: On-demand probe triggers with rate-limiting protection to prevent denial-of-service against internal hardware.
- **Rich Interactive Glassmorphism UI**:
  - Live summary stat cards (Online, Offline, High Latency, Avg RTT).
  - Donut distribution charts and responsive line charts (Chart.js).
  - Search, filter by type/status, and sortable device data table.
  - Interactive Star Network Topology map with live status coloring and node tooltips.
  - Deep-dive Device Details with latency history and packet telemetry.
  - Analytics exploration with customizable time windows.
  - System configuration panel with runtime-adjustable monitoring thresholds.
- **Zero Heavy Dependencies**: Built with pure standard Python, lightweight Flask, and native SQLite (WAL mode enabled).

---

## 🏗️ High-Level System Architecture

```
                    +------------------------------------------+
                    |           Web Browser (Client)           |
                    |   Glassmorphism UI / Chart.js / Vanilla   |
                    +--------------------+---------------------+
                                         |
                                HTTP / REST API
                                         |
                    +--------------------v---------------------+
                    |           Flask Application              |
                    |   - Web Routes (HTML / Jinja2)           |
                    |   - REST API Endpoints (/api/*)          |
                    |   - Input Validation & Sanitization      |
                    +----------+--------------------+----------+
                               |                    |
            Reads & Writes     |                    | Dispatches Probes
                               v                    v
         +----------------------------+   +----------------------------+
         |     SQLite Database        |   |    Background Worker Pool  |
         |  - devices                 |   |  - ThreadPoolExecutor      |
         |  - probe_results (WAL)     |   |  - Daemon monitor thread   |
         |  - events / alerts         |   |  - Platform Ping Service   |
         |  - settings                |   +-------------+--------------+
         +----------------------------+                 |
                                                        | ICMP Echo Request / Reply
                                                        v
                                          +----------------------------+
                                          | Network Devices / Targets  |
                                          | Routers, PCs, 8.8.8.8, ... |
                                          +----------------------------+
```

---

## 📋 Theoretical Computer Networks (CN) Alignment

This project directly demonstrates fundamental concepts from the university Computer Networks syllabus:

| CN Syllabus Concept | Project Implementation |
|---|---|
| **Network Layer & ICMP (RFC 792)** | Sends ICMP Type 8 (Echo Request) and processes ICMP Type 0 (Echo Reply) to verify Layer 3 connectivity. |
| **Round-Trip Time (RTT) & Jitter** | Calculates elapsed transmission delay between sender and receiver; measures variations in response latency. |
| **Application Layer & DNS (RFC 1035)** | Resolves Fully Qualified Domain Names (FQDNs) to IPv4/IPv6 addresses, handling DNS resolution errors. |
| **Network Reliability & SLA Math** | Computes availability percentage: `Availability % = (Reachable Probes / Total Probes) * 100`. |
| **Logical Network Topologies** | Visualizes nodes arranged in a Star Topology relative to the central NetWatch monitoring station. |
| **Transport / Socket Timeout Handling** | Implements bounded wait periods preventing hung threads on unresponsive network segments. |

---

## ⚙️ Prerequisites

- **Python**: Version 3.10, 3.11, or 3.12 (compatible with Python 3.13)
- **Operating System**:
  - Windows 10/11 (fully supported via `ping -n 1 -w <ms>`)
  - Linux (Ubuntu, Debian, Fedora, Arch via `ping -c 1 -W <sec>`)
  - macOS (via `ping -c 1 -W <ms>`)
- **Network Permissions**: Standard user privileges (NetWatch uses the operating system's built-in `ping` binary, which operates with unprivileged raw socket elevation on all major platforms).

---

## 🚀 Quickstart Guide

### 1. Clone or Open the Repository
```bash
cd "c:\Users\suyu8\OneDrive\ドキュメント\cnproject\network-monitor"
```

### 2. Set Up Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Automated Test Suite
Verify that all 80 unit, integration, and API tests pass:
```bash
pytest -v
```

### 5. Start the Application
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 📡 REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | `GET` | Health check endpoint returning status, uptime, and database connectivity. |
| `/api/devices` | `GET` | List all monitored devices with their current status and latest ping metrics. |
| `/api/devices` | `POST` | Register a new device (`name`, `target`, `device_type`, `monitoring_interval`, etc.). |
| `/api/devices/<id>` | `GET` | Retrieve detailed configuration and telemetry for a specific device. |
| `/api/devices/<id>` | `PUT` | Update a device's label, IP address/hostname, interval, or metadata. |
| `/api/devices/<id>` | `DELETE` | Remove a device and cascade-delete all associated historical probes and events. |
| `/api/devices/<id>/test` | `POST` | Trigger an immediate manual ping check (rate-limited). |
| `/api/devices/<id>/toggle` | `PATCH` | Enable or disable automatic background polling for a device. |
| `/api/dashboard` | `GET` | Aggregate stats: online/offline counts, high latency counts, fleet average RTT. |
| `/api/analytics` | `GET` | Time-series latency charts, availability trends, min/max/avg stats over `?range=`. |
| `/api/events` | `GET` | Query state-change event logs (`device_offline`, `device_recovered`, `high_latency`). |
| `/api/events/<id>/read` | `PATCH`| Mark an alert notification as acknowledged/read. |
| `/api/events/read-all` | `POST` | Mark all unread notifications as read. |
| `/api/settings` | `GET` | Fetch system-wide monitoring defaults and retention parameters. |
| `/api/settings` | `PUT` | Update operational thresholds and ping timeout configurations. |

---

## 🛠️ Configuration Options

Configuration is managed via `config.py` and environment variables (`.env`):

| Variable | Default | Purpose |
|---|---|---|
| `FLASK_ENV` | `development` | Environment mode (`development`, `testing`, `production`). |
| `SECRET_KEY` | Auto-generated | Flask session encryption key. |
| `DATABASE_PATH` | `instance/network_monitor.db` | File path for SQLite database. |
| `DEFAULT_MONITORING_INTERVAL` | `30` | Default probe cadence in seconds per device. |
| `MIN_MONITORING_INTERVAL` | `5` | Hard lower bound preventing network flooding. |
| `MAX_MONITORING_INTERVAL` | `300` | Upper bound for device polling cycles. |
| `DEFAULT_PING_TIMEOUT` | `5` | Subprocess timeout limit before classifying as timeout failure. |
| `DATA_RETENTION_DAYS` | `30` | Auto-cleanup horizon for historical probe entries. |
| `DASHBOARD_REFRESH_INTERVAL` | `5000` | Polling interval (ms) for live dashboard UI refreshes. |

---

## 🔍 Troubleshooting

- **Target shows 'Offline' immediately after creation:**
  - Devices initially start in `unknown` status until the first scheduled polling cycle executes (within their configured interval), or until you click the **"Ping Now"** button.
- **Firewall drops ICMP Echo Requests:**
  - Some modern firewalls and cloud servers (e.g., certain AWS EC2 instances) drop inbound ICMP Echo requests by default. Ensure test targets (such as `127.0.0.1`, `8.8.8.8`, or local gateway `192.168.1.1`) allow ICMP.
- **PowerShell Script Execution Restriction:**
  - If `.\venv\Scripts\Activate.ps1` gives an execution policy error on Windows, run:
    `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## 📜 Academic Honesty & Disclaimer

This project was conceived and structured for university-level Computer Networks coursework. All network telemetry operations conform to standard network utility conventions. The software performs non-destructive ICMP connectivity checks only and is intended for network diagnostics, laboratory simulation, and infrastructure administration.
