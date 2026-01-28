import subprocess, shutil, socket, json, datetime, os, re, sys


OUTPUT_DIRECTORY = "output"          # Folder to store JSON reports
LOG_FILE_PATH = "system_health.log"  # Rolling log file
MAX_LOG_ENTRIES = 100                # Keep only last N log lines
TOP_PROCESS_COUNT = 5                # Number of top processes to show

# ---------------- PLATFORM DETECTION ----------------
# Used to branch OS-specific logic safely to make our script platform independent

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

os.makedirs(OUTPUT_DIRECTORY, exist_ok=True) # Ensure output directory exists

# ---------------- UTILITY FUNCTIONS ----------------

def run_command(command): # Executes a shell command safely and returns stdout as string & Errors are suppressed to avoid script crashes.

    try:
        return subprocess.check_output(
            command,
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""

# ---------------- CORE METRICS ----------------

def current_timestamp():

    return datetime.datetime.now().isoformat(timespec="seconds") # Returns ISO-8601 timestamp (seconds precision)

def get_cpu_usage(): # Returns CPU usage percentage - Windows using CIM LoadPercentage & Linux/Mac: Approximated using load average

    if IS_WINDOWS:
        output = run_command(
            'powershell "(Get-CimInstance Win32_Processor | '
            'Measure-Object LoadPercentage -Average).Average"'
        )
        return f"{output}%" if output.isdigit() else "N/A"

    try:
        load_1min, _, _ = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        return f"{int((load_1min / cpu_count) * 100)}%"
    except Exception:
        return "N/A"

def get_memory_usage(): #Returns (used_memory, total_memory) in MB. Uses OS-specific commands

    if IS_WINDOWS:
        output = run_command(
            'powershell "$m=Get-CimInstance Win32_OperatingSystem; '
            '[math]::Round(($m.TotalVisibleMemorySize-$m.FreePhysicalMemory)/1024),'
            '[math]::Round($m.TotalVisibleMemorySize/1024)"'
        ).split()
        if len(output) == 2:
            return f"{output[0]}MB", f"{output[1]}MB"

    if IS_LINUX:
        meminfo = open("/proc/meminfo").read()
        total = int(re.search(r"MemTotal:\s+(\d+)", meminfo).group(1)) // 1024
        available = int(re.search(r"MemAvailable:\s+(\d+)", meminfo).group(1)) // 1024
        return f"{total - available}MB", f"{total}MB"

    if IS_MACOS:
        total = int(run_command("sysctl -n hw.memsize")) // (1024 ** 2)
        vm_stat = run_command("vm_stat")
        free_pages = int(re.search(r"Pages free:\s+(\d+)", vm_stat).group(1))
        page_size = int(run_command("sysctl -n hw.pagesize"))
        used = total - (free_pages * page_size) // (1024 ** 2)
        return f"{used}MB", f"{total}MB"

    return "N/A", "N/A"

def get_disk_usage(): # Returns (used, total, percentage). Based on OS.

    root_path = "C:\\" if IS_WINDOWS else "/"
    total, used, _ = shutil.disk_usage(root_path)
    return (
        f"{used // (1024 ** 3)}GB",
        f"{total // (1024 ** 3)}GB",
        f"{int((used / total) * 100)}%"
    )

def get_uptime(): # Returns system uptime as 'X Days Y Hours'.

    try:
        now = datetime.datetime.now()

        if IS_WINDOWS:
            output = run_command(
                'powershell "(Get-CimInstance Win32_OperatingSystem).'
                'LastBootUpTime.ToString(\'yyyy-MM-dd HH:mm:ss\')"'
            )
            boot_time = datetime.datetime.strptime(output, "%Y-%m-%d %H:%M:%S")

        elif IS_LINUX:
            uptime_seconds = float(open("/proc/uptime").read().split()[0])
            boot_time = now - datetime.timedelta(seconds=uptime_seconds)

        elif IS_MACOS:
            seconds = int(
                re.search(r"sec = (\d+)", run_command("sysctl -n kern.boottime")).group(1)
            )
            boot_time = datetime.datetime.fromtimestamp(seconds)

        else:
            return "N/A"

        delta = now - boot_time
        return f"{delta.days} Days {delta.seconds // 3600} Hours"

    except Exception:
        return "N/A"

# ---------------- OPTIONAL METRICS ----------------

def check_network_status(): # Checks basic internet connectivity

    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return "UP"
    except Exception:
        return "DOWN"

def get_top_processes(): # Returns top CPU & memory consuming processes. Output is structured JSON (clean, not raw command output).

    def parse_process_list(command, metric_key):
        return [
            {"pid": int(p[0]), "name": p[1], metric_key: float(p[2])}
            for p in (line.split() for line in run_command(command).splitlines()[1:])
            if len(p) >= 3
        ]

    if IS_WINDOWS:
        cpu = json.loads(run_command(
            f'powershell "Get-Process | Sort CPU -Desc | '
            f'Select -First {TOP_PROCESS_COUNT} Id,Name,CPU | ConvertTo-Json"'
        ) or "[]")

        memory = json.loads(run_command(
            f'powershell "Get-Process | Sort PM -Desc | '
            f'Select -First {TOP_PROCESS_COUNT} Id,Name,PM | ConvertTo-Json"'
        ) or "[]")

        return {
            "cpu": [
                {"pid": p["Id"], "name": p["Name"], "cpu": round(p["CPU"], 2)}
                for p in cpu
            ],
            "memory": [
                {"pid": p["Id"], "name": p["Name"], "mem": round(p["PM"] / (1024 ** 2), 2)}
                for p in memory
            ]
        }

    return {
        "cpu": parse_process_list(
            f"ps -eo pid,comm,%cpu --sort=-%cpu | head -n {TOP_PROCESS_COUNT + 1}",
            "cpu"
        ),
        "memory": parse_process_list(
            f"ps -eo pid,comm,%mem --sort=-%mem | head -n {TOP_PROCESS_COUNT + 1}",
            "mem"
        )
    }
# ---------------- CRITICAL PROCESS CHECK ----------------
# Validates presence of important OS-level processes/services

CRITICAL_PROCESSES = {           # Predefining a set of specific services for different OS types
    "windows": ["explorer.exe", "svchost.exe", "lsass.exe"],
    "linux": ["systemd", "sshd"],
    "macos": ["launchd"]
}

def get_running_process_names():  # Returns a set of running process names
    if IS_WINDOWS:
        output = run_command(
            'powershell "Get-Process | Select -ExpandProperty Name"'
        )
        return {p.lower() + ".exe" for p in output.splitlines()}

    output = run_command("ps -eo comm")
    return {p.lower() for p in output.splitlines()}

def check_critical_processes():  # Checks if critical processes are running
    running_processes = get_running_process_names()

    if IS_WINDOWS:
        required = CRITICAL_PROCESSES["windows"]
    elif IS_LINUX:
        required = CRITICAL_PROCESSES["linux"]
    elif IS_MACOS:
        required = CRITICAL_PROCESSES["macos"]
    else:
        return {}

    return {
        process: (
            "RUNNING" if process.lower() in running_processes else "NOT_RUNNING"
        )
        for process in required
    }

# ---------------- LOGGING ----------------

def append_log_with_rotation(log_line): #Appends a log entry and trims file to last MAX_LOG_ENTRIES lines.

    existing_lines = open(LOG_FILE_PATH).readlines() if os.path.exists(LOG_FILE_PATH) else []
    with open(LOG_FILE_PATH, "w") as file:
        file.writelines((existing_lines + [log_line + "\n"])[-MAX_LOG_ENTRIES:])

# ---------------- MAIN BLOCK----------------

def main():
    timestamp = current_timestamp()
    cpu = get_cpu_usage()
    memory_used, memory_total = get_memory_usage()
    disk_used, disk_total, disk_percent = get_disk_usage()
    uptime = get_uptime()

    header = (
        "Timestamp|CPU|UsedMemory|TotalMemory|"
        "UsedDiskSpace|TotalDiskSpace|DiskUsedPercent|Uptime"
    )

    log_line = (
        f"{timestamp}|{cpu}|{memory_used}|{memory_total}|"
        f"{disk_used}|{disk_total}|{disk_percent}|{uptime}"
    )
    print("--- CORE FUNCTIONALITY --- \n")
    print(header)
    print(log_line)

    print('\n--- LOG LINES APPENDED TO system_health.log file ---')
    append_log_with_rotation(log_line)

    report = {
        "timestamp": timestamp,
        "cpu": cpu,
        "memory": {"used": memory_used, "total": memory_total},
        "disk": {"used": disk_used, "total": disk_total, "percent": disk_percent},
        "uptime": uptime,
        "network": check_network_status(),
        "top_processes": get_top_processes(),
        "critical_processes": check_critical_processes()
    }

    print("\n--- OPTIONAL JSON FEATURE INCLUDING NETWORK CONNECTIVITY, TOP 5 PROCESS, SPECIFIC CRITICAL PROCESS, LOGGING ---")
    print(json.dumps(report, indent=2))

    with open(os.path.join(OUTPUT_DIRECTORY, "system_report.json"), "w") as file:
        json.dump(report, file, indent=2)

if __name__ == "__main__":
    main()
