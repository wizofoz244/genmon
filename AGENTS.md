# Genmon Agent Rules & Guidelines

These guidelines apply specifically to working within the Genmon repository and local generator monitoring customizations. Global SDLC, git branch safety, and developer velocity protocols are inherited from global `GEMINI.md`.

---

## 1. Project Context & Purpose
- **Core System**: Python-based generator monitoring daemon communicating with Generac Evolution/Nexus/H-100 controllers via serial Modbus / TCP.
- **Local Integrations**: Home Assistant MQTT, notification handlers, health monitoring, and outage/exercise duration analysis.

---

## 2. Coding & Scripting Conventions
- **Upstream Compatibility**: When modifying or patching core files in `genmonlib/`, maintain clean separation or document patches clearly to avoid merge conflicts with upstream releases.
- **Python Compatibility**: Code must remain compatible with Python 3.7+ running on ARM Linux (Raspberry Pi Raspbian) as well as macOS local test environments.
- **Data Integrity**: Never mutate or truncate raw controller logs (`maintlog.json`, `statusHistory.csv`) during processing scripts. Always work on copies or use idempotent parsing routines.

---

## 3. Verification Standards
- When creating or modifying data processing or notification scripts, verify parsing against sample status records:
  ```bash
  python3 -m py_compile <script_name>.py
  ```
- If altering core communication loops, verify that exceptions are logged defensively and do not crash the long-running daemon threads.
