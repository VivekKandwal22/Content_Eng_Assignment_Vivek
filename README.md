--- System Health Monitoring Script (Content Engineering Assignment) ---

Overview:
This script collects key system health metrics including CPU usage, memory usage, disk usage, uptime, and network connectivity. It is designed to be safe, read-only, and lightweight for execution on production endpoints (OS Agnostic). Includes comments and self defined variables for ease of reading and better understanding.

How to Run:

- Requires Python 3.x (Check your Python version using 'python --version' command)
- git clone <repo-url> to download and run it locally on a IDE
- Run with: python3 system_health_monitor.py
- Any IDE for ease of code reading and debugging (Vscode or Pycharm)


📦 Prerequisites/ Dependencies
Built-in Python Libraries Only

This script does NOT use any third-party packages relies exclusively on standard Python libraries:

1. shutil – disk usage calculation
2. socket – network connectivity check
3. json – structured output
4. datetime – timestamps & uptime calculations
5. os – platform detection & filesystem access
6. re – regex parsing (memory & uptime)
7. sys – OS/platform identification
8. subprocess – execute OS commands safely

➡️ No pip install required.

Optional Features Implemented:
- Network connectivity check
- Top 5 processes by memory and CPU usage
- Check for specific critical processes (Using pre-defined list)
- JSON export
- Logging in a text based log file (up to a number of lines threshold)

Notes:
- Script avoids privileged operations
- All metrics are collected using native OS interfaces
- Output is formatted for easy ingestion by automation platforms
