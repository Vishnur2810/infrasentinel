#!/usr/bin/env python3
"""InfraSentinel agent: read-only security checks for a server or PC YOU own (Linux, Windows; basic checks on macOS).

What it does
  Looks at this server's own settings and state, then sends a short report to your
  InfraSentinel dashboard. It never changes settings or installs packages. The only traffic to other machines is one
  connection attempt to your router on ports 21 and 23 (skip with --no-network).

What it checks (Linux and Windows in full; macOS: ports, firewall, FileVault, updates, Gatekeeper, SIP, admins, backups)
  - Services open to the network (from the local socket table)
  - SSH: password logins, direct administrator (root) login
  - Waiting security updates, and whether automatic updates are on
  - Whether the operating system still receives security updates
  - Whether a firewall service is active
  - Extra administrator accounts, size of the admin (sudo) group
  - Empty passwords and readable password files (only when run as root)
  - Whether any backup tool is present
  - Other devices on the same network (from this machine's neighbour/ARP table) and whether the
    router accepts insecure Telnet/FTP logins (one connection attempt each; --no-network to skip)
  - Security logs: failed logins and where they come from, root sign-ins,
    failed administrator (sudo) attempts, new accounts, recent system errors
    (a short summary plus up to 15 example lines; use --no-logs to skip)

What it sends
  Hostname, OS name, this machine's IP addresses, the list of listening services,
  and the findings below. Use --dry-run to print the report without sending it.

Usage
  python3 agent.py --server http://DASHBOARD:8765 --token TOKEN            # check once
  python3 agent.py --server ... --token ... --install                      # also re-check every 6 hours (cron, current user)
  python3 agent.py --uninstall                                             # remove the schedule and files
  python3 agent.py --dry-run                                               # show the report, send nothing
  python3 agent.py --server ... --token ... --watch --every 2              # stay running; full re-check every 2 hours
"""
import argparse, hashlib, ipaddress, json, os, platform, re, shutil, socket, subprocess, sys, time, urllib.request, urllib.error

VERSION = "0.5"
HOME_DIR = os.path.join(os.path.expanduser("~"), ".infrasentinel")

# port -> (name, dashboard group, severity when open to the network, category, plain risk)
PORTS = {
    21: ("FTP file transfer", "file", 7.5, "encryption", "sends passwords and files unencrypted"),
    22: ("SSH remote login", "remote", 5.0, "remote", "remote login is open; attackers try passwords against it"),
    23: ("Telnet", "remote", 9.0, "encryption", "sends logins unencrypted and is obsolete"),
    80: ("Website (HTTP)", "web", 3.0, "encryption", "a website without encryption"),
    111: ("RPC portmapper", "file", 5.0, "misconfig", "reveals internal services and is used in attacks"),
    135: ("Windows RPC endpoint mapper", "other", 5.0, "misconfig", "Windows remote procedure calls; should not be reachable from outside"),
    5985: ("Windows Remote Management (WinRM, HTTP)", "remote", 7.0, "remote", "remote command access to this PC"),
    5986: ("Windows Remote Management (WinRM, HTTPS)", "remote", 5.5, "remote", "remote command access to this PC"),
    139: ("Windows file sharing (NetBIOS)", "file", 7.5, "misconfig", "file sharing open to the network"),
    445: ("Windows file sharing (SMB)", "file", 7.5, "misconfig", "a common ransomware entry point"),
    1433: ("SQL Server database", "data", 7.5, "misconfig", "database reachable from the network"),
    2375: ("Docker control API (no encryption)", "remote", 9.8, "apis", "gives full control of the machine to anyone who reaches it"),
    3306: ("MySQL / MariaDB database", "data", 7.5, "misconfig", "database reachable from the network"),
    3389: ("Remote Desktop", "remote", 8.1, "remote", "a top entry point for ransomware"),
    5432: ("PostgreSQL database", "data", 7.5, "misconfig", "database reachable from the network"),
    5900: ("VNC remote screen", "remote", 8.0, "remote", "remote screen control, often weakly protected"),
    6379: ("Redis database", "data", 8.5, "misconfig", "has no password by default"),
    8888: ("Jupyter notebook", "remote", 7.5, "apis", "can run any code if its access token leaks"),
    9200: ("Elasticsearch", "data", 8.0, "misconfig", "has caused many data leaks when left open"),
    11434: ("Ollama AI API", "data", 6.0, "apis", "AI API with no login by default"),
    27017: ("MongoDB database", "data", 8.0, "misconfig", "has caused many data leaks when left open"),
}
EXPECTED_WEB = {80, 443, 8080, 8443}


def run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except Exception:
        return None, ""


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def os_release():
    d = {}
    for line in (read("/etc/os-release") or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"')
    return d


def agent_id():
    seed = (read("/etc/machine-id") or read("/var/lib/dbus/machine-id") or "").strip()
    if not seed and os.name == "nt":
        seed = str(reg(r"SOFTWARE\Microsoft\Cryptography", "MachineGuid") or "")
    if not seed:
        import uuid
        seed = str(uuid.getnode())
    return hashlib.sha256((seed + socket.gethostname()).encode()).hexdigest()[:16]


def ip_addresses():
    ips = set()
    code, out = run(["hostname", "-I"], 5)
    ips.update(out.split())
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ips.add(info[4][0])
    except Exception:
        pass
    return sorted(i for i in ips if not i.startswith(("127.", "::1", "fe80")))


def has_public_ip(ips):
    for i in ips:
        try:
            a = ipaddress.ip_address(i)
            if a.is_global:
                return True
        except ValueError:
            pass
    return False


def listeners():
    """{port: exposed_bool} from the local socket table."""
    out = {}
    code, txt = run(["ss", "-H", "-tln"], 10)
    if txt:
        for line in txt.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            addr, _, port = parts[3].rpartition(":")
            if port.isdigit():
                addr = addr.strip("[]").split("%")[0]
                p = int(port)
                out[p] = out.get(p, False) or not (addr.startswith("127.") or addr == "::1")
        return out
    code, txt = run(["netstat", "-an"], 10)          # macOS / Windows / older Linux
    for line in txt.splitlines():
        if "LISTEN" not in line.upper() or "tcp" not in line.lower():
            continue
        for tok in line.split():
            m = re.match(r"^(.*)[.:](\d+)$", tok)
            if m and m.group(2).isdigit() and ("." in m.group(1) or "*" in m.group(1) or ":" in m.group(1) or m.group(1) == ""):
                addr, p = m.group(1), int(m.group(2))
                out[p] = out.get(p, False) or not (addr.startswith("127.") or addr in ("::1", "[::1]"))
                break
    return out


def sshd_settings():
    files = ["/etc/ssh/sshd_config"]
    d = "/etc/ssh/sshd_config.d"
    if os.path.isdir(d):
        files = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".conf")] + files
    txt = "\n".join(t for t in (read(f) for f in files) if t)
    if not txt:
        return None
    get = lambda key: (re.findall(rf"^\s*{key}\s+(\S+)", txt, re.M | re.I) or [None])[0]   # first value wins in sshd
    return {"PasswordAuthentication": (get("PasswordAuthentication") or "default (yes)").lower(),
            "PermitRootLogin": (get("PermitRootLogin") or "default (prohibit-password)").lower()}


def pending_updates():
    if shutil.which("apt"):
        code, out = run(["apt", "list", "--upgradable"], 60)
        lines = [l for l in out.splitlines() if "upgradable" in l]
        sec = [l.split("/")[0] for l in lines if "-security" in l]
        return {"manager": "apt", "total": len(lines), "security": len(sec), "packages": sec[:25]}
    if shutil.which("dnf") or shutil.which("yum"):
        pm = "dnf" if shutil.which("dnf") else "yum"
        code, out = run([pm, "-q", "check-update"], 120)
        total = len([l for l in out.splitlines() if l.strip() and not l.startswith((" ", "Obsoleting"))])
        code2, sec = run([pm, "-q", "updateinfo", "list", "--security"], 120)
        rows = [l.split() for l in sec.splitlines() if l.strip()]
        return {"manager": pm, "total": total, "security": len(rows),
                "packages": sorted({r[-1] for r in rows if r})[:25], "advisories": sorted({r[0] for r in rows if r})[:25]}
    return None


def auto_updates():
    if shutil.which("dpkg-query"):
        code, st = run(["dpkg-query", "-W", "-f=${Status}", "unattended-upgrades"], 10)
        conf = read("/etc/apt/apt.conf.d/20auto-upgrades") or ""
        return "install ok installed" in st and re.search(r'Unattended-Upgrade\s+"1"', conf) is not None
    if shutil.which("systemctl") and (shutil.which("dnf") or shutil.which("yum")):
        for t in ("dnf-automatic.timer", "dnf-automatic-install.timer", "yum-cron"):
            code, out = run(["systemctl", "is-enabled", t], 10)
            if out.strip() == "enabled":
                return True
        return False
    return None


def os_support(osr):
    """Return a reason string if this OS no longer gets standard security updates (as of 2026)."""
    ident, ver = osr.get("ID", ""), osr.get("VERSION_ID", "")
    try:
        if ident == "ubuntu":
            yy, mm = (int(x) for x in ver.split(".")[:2])
            lts = mm == 4 and yy % 2 == 0
            if lts and yy < 22:
                return "Ubuntu LTS releases before 22.04 are out of standard support"
            if not lts and (yy, mm) < (26, 10):
                return "this short-term Ubuntu release is out of support"
        if ident == "debian" and int(ver.split(".")[0]) <= 11:
            return "Debian 11 and older are out of security support"
        if ident == "centos":
            return "CentOS Linux 7/8 and CentOS Stream 8 are end of life"
        if ident in ("rhel", "ol", "rocky", "almalinux") and int(ver.split(".")[0]) <= 7:
            return "version 7 and older are out of standard support"
    except Exception:
        return None
    return None


def firewall_active():
    if not shutil.which("systemctl"):
        return None
    for svc in ("ufw", "firewalld", "nftables"):
        code, out = run(["systemctl", "is-active", svc], 10)
        if out.strip() == "active":
            if svc == "ufw" and os.geteuid() == 0:
                c2, st = run(["ufw", "status"], 10)
                if "inactive" in st:
                    continue
            return svc
    return False


LOG_PATTERNS = {
    "failed": re.compile(r"Failed (?:password|publickey) for (invalid user )?(\S+) from (\S+)"),
    "invalid": re.compile(r"Invalid user (\S*) from (\S+)"),
    "accepted": re.compile(r"Accepted (password|publickey|keyboard-interactive/pam) for (\S+) from (\S+)"),
    "sudo_fail": re.compile(r"sudo(?:\[\d+\])?:.*(?:authentication failure|incorrect password attempt)", re.I),
    "sudo_cmd": re.compile(r"sudo(?:\[\d+\])?:\s+(\S+) : .*COMMAND="),
    "new_user": re.compile(r"new user: name=([^,\s]+)"),
    "pam_fail": re.compile(r"pam_unix\((?!sudo)[^)]*\): authentication failure"),
}


def _tail(path, max_lines=6000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 1_500_000))
            return f.read().decode("utf-8", "replace").splitlines()[-max_lines:]
    except Exception:
        return None


def read_logs():
    """Read recent security-relevant log lines (read-only) and return a digest, or None if unreadable."""
    lines, source = None, None
    if shutil.which("journalctl"):
        code, out = run(["journalctl", "-q", "--no-pager", "-o", "short-iso", "--since", "7 days ago",
                         "SYSLOG_FACILITY=4", "SYSLOG_FACILITY=10"], 40)
        if code == 0 and out.strip():
            lines, source = out.splitlines()[-20000:], "system journal (auth), last 7 days"
    if lines is None:
        for p in ("/var/log/auth.log", "/var/log/secure"):
            t = _tail(p)
            if t:
                lines, source = t, f"{p} (most recent lines)"
                break
    if lines is None:
        return None
    from collections import Counter
    ips, users, acc_users = Counter(), Counter(), Counter()
    d = {"source": source, "lines_read": len(lines), "failed_logins": 0, "accepted_logins": 0, "root_logins": 0,
         "sudo_failures": 0, "sudo_commands": 0, "local_login_failures": 0, "new_users": []}
    sample = []
    for l in lines:
        m = LOG_PATTERNS["failed"].search(l)
        if m:
            d["failed_logins"] += 1; users[m.group(2)] += 1; ips[m.group(3)] += 1; sample.append(l); continue
        m = LOG_PATTERNS["invalid"].search(l)
        if m:
            users[m.group(1) or "(blank)"] += 1; ips[m.group(2)] += 1; continue
        m = LOG_PATTERNS["accepted"].search(l)
        if m:
            d["accepted_logins"] += 1; acc_users[m.group(2)] += 1
            if m.group(2) == "root":
                d["root_logins"] += 1; sample.append(l)
            continue
        if LOG_PATTERNS["sudo_fail"].search(l):
            d["sudo_failures"] += 1; sample.append(l); continue
        if LOG_PATTERNS["sudo_cmd"].search(l):
            d["sudo_commands"] += 1; continue
        m = LOG_PATTERNS["new_user"].search(l)
        if m:
            d["new_users"].append(m.group(1)); sample.append(l); continue
        if LOG_PATTERNS["pam_fail"].search(l):
            d["local_login_failures"] += 1
    d["top_source_ips"] = ips.most_common(5)
    d["usernames_tried"] = users.most_common(6)
    d["accepted_by_user"] = acc_users.most_common(5)
    d["new_users"] = sorted(set(d["new_users"]))[:10]
    # recent serious system errors (last 24 h), de-duplicated
    if shutil.which("journalctl"):
        code, out = run(["journalctl", "-q", "--no-pager", "-p", "3", "--since", "24 hours ago", "-o", "cat"], 30)
        if code == 0:
            errs = [e.strip() for e in out.splitlines() if e.strip()]
            d["system_errors_24h"] = len(errs)
            d["top_system_errors"] = [f"{n}x {msg[:160]}" for msg, n in Counter(errs).most_common(5)]
    d["sample_lines"] = [s[:220] for s in sample[-15:]]
    return d


def add_log_findings(add, digest, expo, asset, admin_name):
    """Turn a log digest (same shape on Linux and Windows) into findings."""
    n = digest.get("failed_logins") or 0
    if n >= 20:
        add("log-bruteforce", f"Someone tried to guess sign-in passwords {n} times", 8.5 if n >= 200 else 7.5, "remote",
            expo, asset, top_source_ips=digest.get("top_source_ips"), usernames_tried=digest.get("usernames_tried"),
            log_source=digest.get("source"), risk="automated password guessing; one weak password is enough to get in")
    rl = digest.get("root_logins") or 0
    if rl:
        add("log-root", f"The administrator ({admin_name}) account signed in remotely {rl} time{'s' if rl != 1 else ''}", 7.0,
            "excessive", expo, asset, log_source=digest.get("source"),
            risk="remote administrator sign-ins make it hard to know who did what")
    sf = digest.get("sudo_failures") or 0
    if sf >= 5:
        add("log-sudo", f"{sf} failed attempts to use administrator rights", 6.0, "weakpw",
            log_source=digest.get("source"), risk="someone may be guessing an administrator password")
    if digest.get("new_users"):
        add("log-newuser", f"New user account(s) created recently: {', '.join(digest['new_users'][:5])}", 5.0,
            "accesscontrol", accounts=digest["new_users"], log_source=digest.get("source"),
            note="If you created these yourself, mark this as not applicable.")


# ---------------- Windows ----------------
def is_admin():
    if os.name == "nt":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def ps(script, timeout=60):
    """Run a PowerShell snippet; return parsed JSON, plain text, or None on error."""
    code, out = run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                     "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; " + script], timeout)
    out = (out or "").strip()
    if code != 0 or not out:
        return None
    try:
        return json.loads(out)
    except Exception:
        return out


def reg(path, name, hive="HKLM"):
    try:
        import winreg
        h = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}[hive]
        with winreg.OpenKey(h, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


def as_list(x):
    return [] if x is None else x if isinstance(x, list) else [x]


def win_build():
    try:
        return int(platform.version().split(".")[-1])
    except Exception:
        return 0


def win_os_support(build, edition):
    """Reason string if this Windows version no longer gets security updates for Home/Pro (as of late 2026)."""
    biz = (edition or "").lower().startswith(("enterprise", "education", "iotenterprise"))
    if build and build < 22000:
        return "Windows 10 reached end of support in October 2025 (extended updates for home users end in October 2026)"
    if build in (22000, 22621):
        return "this Windows 11 version (21H2/22H2) no longer receives security updates"
    if build == 22631 and not biz:
        return "Windows 11 23H2 Home and Pro stopped receiving security updates in November 2025"
    if 26100 <= build < 26200 and not biz:
        return "Windows 11 24H2 Home and Pro support ends in October 2026; update to the latest version"
    return None


def win_firewall():
    """{'Domain': True/False, 'Private': ..., 'Public': ...} or None."""
    code, out = run(["netsh", "advfirewall", "show", "allprofiles", "state"], 20)
    if not out:
        return None
    res, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"^\s*(Domain|Private|Public) Profile", line, re.I)
        if m:
            cur = m.group(1).title()
        m = re.match(r"^\s*State\s+(\S+)", line, re.I)
        if m and cur:
            res[cur] = m.group(1).upper() == "ON"
    return res or None


def win_logs(as_admin):
    from collections import Counter
    d = {"source": "Windows event logs (Security + System), last 7 days", "failed_logins": None, "accepted_logins": None,
         "root_logins": 0, "sudo_failures": 0, "new_users": [], "top_source_ips": [], "usernames_tried": [], "accepted_by_user": []}
    if as_admin:
        sec = ps(r"""
$s=(Get-Date).AddDays(-7)
$f=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$s} -MaxEvents 4000 -ErrorAction SilentlyContinue)
$o=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$s} -MaxEvents 4000 -ErrorAction SilentlyContinue | Where-Object { $_.Properties[8].Value -in 3,10 })
$n=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4720;StartTime=$s} -ErrorAction SilentlyContinue)
[pscustomobject]@{
 failed=@($f | ForEach-Object { [pscustomobject]@{u=[string]$_.Properties[5].Value; ip=[string]$_.Properties[19].Value} })
 ok=@($o | ForEach-Object { [pscustomobject]@{u=[string]$_.Properties[5].Value; ip=[string]$_.Properties[18].Value} })
 newu=@($n | ForEach-Object { [string]$_.Properties[0].Value })
} | ConvertTo-Json -Depth 4 -Compress""", 120)
        if isinstance(sec, dict):
            failed, ok = as_list(sec.get("failed")), as_list(sec.get("ok"))
            ips = Counter(x.get("ip") for x in failed if x.get("ip") not in (None, "", "-", "::1", "127.0.0.1"))
            d.update(failed_logins=len(failed), accepted_logins=len(ok),
                     usernames_tried=Counter(x.get("u") or "(blank)" for x in failed).most_common(6),
                     top_source_ips=ips.most_common(5), accepted_by_user=Counter(x.get("u") for x in ok).most_common(5),
                     root_logins=sum(1 for x in ok if str(x.get("u", "")).lower() == "administrator"),
                     new_users=sorted(set(str(u) for u in as_list(sec.get("newu"))))[:10])
            d["sample_lines"] = [f"4625 failed sign-in: user={x.get('u')} from={x.get('ip')}" for x in failed[:10]]
    else:
        d["source"] = "Windows System event log (run as administrator to include sign-in attempts)"
    sysl = ps(r"""
$e=@(Get-WinEvent -FilterHashtable @{LogName='System';Level=1,2;StartTime=(Get-Date).AddDays(-1)} -MaxEvents 1000 -ErrorAction SilentlyContinue)
[pscustomobject]@{n=$e.Count; top=@($e | Group-Object ProviderName | Sort-Object Count -Descending | Select-Object -First 5 | ForEach-Object { "$($_.Count)x $($_.Name)" })} | ConvertTo-Json -Compress""", 60)
    if isinstance(sysl, dict):
        d["system_errors_24h"] = sysl.get("n")
        d["top_system_errors"] = as_list(sysl.get("top"))
    return d


def check_windows(as_admin, logs=True):
    build = win_build()
    disp = reg(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "DisplayVersion") or ""
    edition = reg(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "EditionID") or ""
    ed_label = {"Core": "Home", "Professional": "Pro"}.get(edition, edition)
    os_name = f"Windows {11 if build >= 22000 else 10} {disp} {ed_label}".replace("  ", " ").strip() + f" (build {build})"
    ips = ip_addresses()
    public = has_public_ip(ips)
    net_expo = "internet" if public else "network"
    findings, services, skipped = [], [], []

    def add(fid, title, severity, category, exposure="internal", asset="host", **details):
        details["category"] = category
        findings.append({"id": fid, "title": title, "severity": severity, "exposure": exposure, "asset": asset, "details": details})

    # Firewall first: it changes how risky open services are
    fw = win_firewall()
    fw_all_on = bool(fw) and all(fw.values())
    if fw is None:
        skipped.append("Windows Firewall status")
    else:
        off = [k for k, v in fw.items() if not v]
        if off:
            add("win-firewall", f"Windows Firewall is turned off for the {', '.join(off)} network profile{'s' if len(off) > 1 else ''}",
                7.5 if "Public" in off else 6.5, "misconfig", net_expo, profiles=fw,
                risk="other devices on the same network can reach every service on this PC",
                how="Settings > Privacy & security > Windows Security > Firewall & network protection")

    # RDP settings
    rdp_on = reg(r"SYSTEM\CurrentControlSet\Control\Terminal Server", "fDenyTSConnections") == 0
    nla = reg(r"SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp", "UserAuthentication")

    # 1. Services open to the network
    socks = listeners()
    noisy = {5040, 7680}            # Windows device-connect and Delivery Optimization services
    for p, exposed in sorted(socks.items()):
        if p >= 49152 or p in noisy:
            continue                # dynamic Windows RPC ports
        name, group, sev, cat, why = PORTS.get(p, (f"Service on port {p}", "other", 4.0, "misconfig",
                                                     "an unidentified service; check what it is and whether it is needed"))
        services.append({"port": p, "name": name, "cat": group, "exposed": bool(exposed)})
        if not exposed or p in (443, 8443) or (p == 3389 and rdp_on):
            continue
        note = "Windows Firewall is on, which usually blocks this from other computers unless a rule allows it." if fw_all_on else \
            "Check whether this service is needed and whether the firewall allows it."
        add(f"port{p}", f"{name} is open to the network (port {p})", round(sev * (0.6 if fw_all_on else 1.0), 1), cat,
            net_expo, f"svc:{p}", port=p, risk=why, note=note)

    if rdp_on:
        if nla == 0:
            add("win-rdp-nla", "Remote Desktop is on without Network Level Authentication", 8.0, "remote", net_expo,
                "svc:3389" if 3389 in socks else "host", risk="attackers can reach the Windows sign-in screen before proving who they are",
                how="Settings > System > Remote Desktop > turn on 'Require devices to use Network Level Authentication'")
        else:
            add("win-rdp", "Remote Desktop is turned on", 5.5, "remote", net_expo, "svc:3389" if 3389 in socks else "host",
                risk="a common target for password guessing and ransomware", how="Settings > System > Remote Desktop")

    # 2. Antivirus
    mp = ps("Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,AntivirusSignatureAge | ConvertTo-Json -Compress", 60)
    if isinstance(mp, dict):
        if mp.get("RealTimeProtectionEnabled") is False or mp.get("AntivirusEnabled") is False:
            add("win-av-off", "Microsoft Defender real-time protection is off", 8.0, "misconfig",
                how="Windows Security > Virus & threat protection > Manage settings > Real-time protection",
                note="If another antivirus product is installed and active, this can be expected.")
        age = mp.get("AntivirusSignatureAge")
        if isinstance(age, int) and age > 7 and mp.get("AntivirusEnabled") is not False:
            add("win-av-old", f"Antivirus definitions are {age} days old", 5.5, "outdated",
                how="Windows Security > Virus & threat protection > Protection updates > Check for updates")
    else:
        av = ps("Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | Select-Object displayName | ConvertTo-Json -Compress", 40)
        if av is None:
            add("win-av-none", "No active antivirus could be found", 8.0, "misconfig",
                note="If you use antivirus that this check cannot see, mark this as not applicable.")

    # 3. Updates
    last = ps("(Get-HotFix | Where-Object InstalledOn | Sort-Object InstalledOn -Descending | Select-Object -First 1).InstalledOn.ToString('yyyy-MM-dd')", 90)
    if isinstance(last, str) and re.match(r"\d{4}-\d{2}-\d{2}$", last):
        days = int((time.time() - time.mktime(time.strptime(last, "%Y-%m-%d"))) // 86400)
        if days > 45:
            add("win-updates", f"No Windows updates have been installed for {days} days", 8.0 if days > 90 else 7.0, "patches",
                last_update=last, how="Settings > Windows Update > Check for updates")
    else:
        skipped.append("last Windows update date")
    if reg(r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", "NoAutoUpdate") == 1:
        add("win-au-off", "Automatic Windows updates are turned off by a policy", 5.0, "outdated",
            risk="new fixes are only installed when someone remembers")

    # 4. Operating system support
    reason = win_os_support(build, edition)
    if reason:
        add("os-eol", f"Unsupported OS: {os_name} is out of (or ending) security support", 8.0 if any(w in reason for w in ("reached", "no longer", "stopped")) else 6.0,
            "unsupporteddev", reason=reason, note="Enterprise and Education editions can have longer support.")

    # 5. Old file-sharing protocol (SMBv1)
    smb1 = ps("(Get-SmbServerConfiguration).EnableSMB1Protocol", 40)
    if smb1 == "True" or smb1 is True:
        add("win-smb1", "The old, unsafe file-sharing protocol SMBv1 is turned on", 8.5, "misconfig", net_expo,
            "svc:445" if 445 in socks else "host", risk="SMBv1 was used by the WannaCry ransomware",
            how="Control Panel > Programs > Turn Windows features on or off > untick 'SMB 1.0/CIFS File Sharing Support'")
    elif smb1 is None and not as_admin:
        skipped.append("SMBv1 setting (run as administrator)")

    # 6. Accounts and permissions
    admins = ps("Get-LocalGroupMember -SID S-1-5-32-544 | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress", 40)
    admins = [a for a in as_list(admins) if isinstance(a, str)]
    if len(admins) > 3:
        add("admins", f"{len(admins)} accounts have administrator rights on this PC", 4.0, "excessive", accounts=admins[:10],
            note="Keep administrator rights to the few people who need them; use standard accounts for daily work.")
    builtin = ps("Get-LocalUser | Where-Object { $_.SID -like '*-500' -or $_.SID -like '*-501' } | Select-Object Name,Enabled,@{n='Rid';e={$_.SID.Value.Split('-')[-1]}} | ConvertTo-Json -Compress", 40)
    for u in as_list(builtin):
        if isinstance(u, dict) and u.get("Enabled"):
            if str(u.get("Rid")) == "500":
                add("win-builtin-admin", "The built-in Administrator account is enabled", 6.0, "excessive", account=u.get("Name"),
                    risk="a well-known account name that attackers try first")
            elif str(u.get("Rid")) == "501":
                add("win-guest", "The Guest account is enabled", 6.5, "accesscontrol", account=u.get("Name"),
                    risk="anyone can sign in without a password")
    if reg(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA") == 0:
        add("win-uac-off", "User Account Control (UAC) is turned off", 7.5, "excessive",
            risk="every program runs with full administrator power", how="Control Panel > User Accounts > Change User Account Control settings")
    elif reg(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "ConsentPromptBehaviorAdmin") == 0:
        add("win-uac-silent", "Windows never asks before making administrator changes", 5.5, "excessive",
            how="Control Panel > User Accounts > Change User Account Control settings")
    code, acc = run(["net", "accounts"], 20)
    m = re.search(r"Minimum password length:\s*(\d+)", acc or "", re.I)
    if m and int(m.group(1)) < 8:
        add("win-pwlen", f"Windows allows short passwords (minimum length is {m.group(1)})", 5.0, "weakpw",
            note="Accounts that sign in with a Microsoft account or PIN may have their own rules.")
    if re.search(r"Lockout threshold:\s*Never", acc or "", re.I):
        add("win-lockout", "There is no lockout after repeated wrong passwords", 5.5, "weakpw",
            risk="attackers can keep guessing passwords without being slowed down")

    # 7. Disk encryption
    bl = ps("(Get-BitLockerVolume -MountPoint $env:SystemDrive).ProtectionStatus.ToString()", 40) if as_admin else None
    if bl == "Off":
        add("win-bitlocker", "The system drive is not encrypted (BitLocker is off)", 6.5, "encryption",
            risk="if this laptop is lost or stolen, its files can be read", how="Settings > Privacy & security > Device encryption (or BitLocker)")
    elif not as_admin:
        skipped.append("disk encryption (run as administrator)")

    # 8. Backups (presence of a backup tool only)
    pf = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    tools = [t for t in ("Veeam", "Acronis", "Macrium", "Backblaze", "Duplicati 2", "Carbonite", "CrashPlan", "Arq", "Cobian Reflector", "EaseUS")
             if any(os.path.isdir(os.path.join(d, t)) for d in pf)]
    tools += [t for t in ("restic", "kopia", "rclone") if shutil.which(t)]
    fh = os.path.isdir(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "FileHistory", "Configuration"))
    if not tools and not fh:
        add("backups", "No backup tool or File History setup was found on this PC", 5.5, "backups",
            looked_for="File History, Veeam, Acronis, Macrium, Backblaze, Duplicati, Carbonite, CrashPlan, Arq, restic",
            note="If you back up another way (for example OneDrive folder backup), confirm restores work and mark this as not applicable.")

    # 9. Event logs
    digest = None
    if logs:
        digest = win_logs(as_admin)
        if digest.get("failed_logins") is None:
            skipped.append("sign-in attempts in the Security log (run as administrator)")
        add_log_findings(add, digest, net_expo, "svc:3389" if 3389 in socks else "host", "Administrator")

    return {"agent_version": VERSION, "agent_id": agent_id(), "hostname": socket.gethostname(), "os": os_name,
            "ip": ", ".join(ips[:4]), "public_ip": public, "as_root": as_admin,
            "checked_at": int(time.time()), "services": services, "findings": findings, "skipped": skipped,
            "logs": digest}


def check(as_root, logs=True):
    if os.name == "nt":
        return check_windows(as_root, logs)
    osr = os_release()
    os_name = osr.get("PRETTY_NAME") or f"{platform.system()} {platform.release()}"
    ips = ip_addresses()
    public = has_public_ip(ips)
    net_expo = "internet" if public else "network"
    findings, services, skipped = [], [], []

    def add(fid, title, severity, category, exposure="internal", asset="host", **details):
        details["category"] = category
        findings.append({"id": fid, "title": title, "severity": severity, "exposure": exposure,
                         "asset": asset, "details": details})

    # 1. Services open to the network
    socks = listeners()
    exposed_ports = sorted(p for p, e in socks.items() if e)
    for p, exposed in sorted(socks.items()):
        name, group, sev, cat, why = PORTS.get(p, (f"Service on port {p}", "other", 4.0, "misconfig",
                                                     "an unidentified service; check what it is and whether it is needed"))
        if p == 443:
            name, group = "Website (HTTPS)", "web"
        services.append({"port": p, "name": name, "cat": group, "exposed": bool(exposed)})
        if not exposed or (p in EXPECTED_WEB and p != 80):
            continue
        if p == 80 and 443 in socks:
            continue  # HTTP alongside HTTPS is usually a redirect
        add(f"port{p}", f"{name} is open to the network (port {p})", sev, cat, net_expo, f"svc:{p}",
            port=p, risk=why, seen_on="all network interfaces",
            note="If a cloud firewall (security group) already blocks this port, mark it as not applicable.")

    # 2. SSH settings
    ssh = sshd_settings()
    if ssh and 22 in socks:
        expo = net_expo if socks.get(22) else "isolated"
        if ssh["PasswordAuthentication"].startswith(("yes", "default")):
            add("ssh-password", "SSH remote login accepts passwords", 7.0, "weakpw", expo, "svc:22",
                setting=f"PasswordAuthentication {ssh['PasswordAuthentication']}", risk="attackers can keep guessing passwords")
        if ssh["PermitRootLogin"] == "yes":
            add("ssh-root", "The administrator (root) account can sign in directly from the network", 7.5, "excessive", expo, "svc:22",
                setting="PermitRootLogin yes", risk="one guessed password gives full control")
    elif ssh is None and 22 in socks:
        skipped.append("SSH settings (config file not readable)")

    # 3. Updates
    up = pending_updates()
    if up is None:
        skipped.append("pending updates (package manager not recognized)")
    else:
        if up["security"] > 0:
            add("sec-updates", f"{up['security']} security patches are waiting to be installed", 8.5 if up["security"] >= 10 else 7.5,
                "patches", "internal", manager=up["manager"], waiting_security=up["security"], waiting_total=up["total"],
                affected_software=up.get("packages", []), advisories=up.get("advisories", []),
                note="Each listed package has a published security fix (known vulnerabilities) that is not installed yet. "
                     "Based on the last package list refresh on this server.")
        elif up["total"] >= 30:
            add("updates", f"{up['total']} software updates are waiting; the system is getting out of date", 5.0, "outdated",
                manager=up["manager"], waiting_total=up["total"])
    au = auto_updates()
    if au is False:
        add("auto-updates", "Automatic security updates are turned off", 4.5, "outdated",
            risk="new fixes are only installed when someone remembers")

    # 4. Operating system support
    reason = os_support(osr)
    if reason:
        add("os-eol", f"Unsupported OS: {os_name} no longer receives regular security updates", 8.0, "unsupporteddev",
            reason=reason, note="Based on published end-of-support dates; extended paid support may apply.")

    # 5. Firewall
    fw = firewall_active()
    if fw is False and exposed_ports:
        add("firewall", "No firewall service is turned on, and services are open to the network", 5.5, "misconfig", net_expo,
            open_ports=exposed_ports[:20], checked="ufw, firewalld, nftables",
            note="If your cloud provider's firewall (security group) protects this server, this may already be covered.")

    # 6. Accounts and permissions
    passwd = read("/etc/passwd") or ""
    uid0 = [l.split(":")[0] for l in passwd.splitlines() if l.count(":") >= 6 and l.split(":")[2] == "0" and l.split(":")[0] != "root"]
    if uid0:
        add("uid0", f"{len(uid0)} extra account(s) have full administrator power", 9.0, "excessive", accounts=uid0[:10])
    group = read("/etc/group") or ""
    admins = set()
    for l in group.splitlines():
        parts = l.split(":")
        if len(parts) >= 4 and parts[0] in ("sudo", "wheel", "admin") and parts[3]:
            admins.update(x for x in parts[3].split(",") if x)
    if len(admins) > 3:
        add("admins", f"{len(admins)} people can act as administrator", 4.0, "excessive", count=len(admins),
            note="Keep administrator rights to the few people who need them.")
    try:
        mode = os.stat("/etc/shadow").st_mode
        if mode & 0o004:
            add("shadow-perm", "The password file can be read by every user on this server", 9.0, "accesscontrol",
                file="/etc/shadow", risk="anyone with an account can try to crack all passwords")
    except Exception:
        pass
    if as_root:
        shadow = read("/etc/shadow") or ""
        empty = [l.split(":")[0] for l in shadow.splitlines() if l.count(":") >= 2 and l.split(":")[1] == ""]
        if empty:
            add("empty-pw", f"{len(empty)} account(s) have no password at all", 9.0, "weakpw", accounts=empty[:10])
    else:
        skipped.append("empty passwords (run with sudo to include)")

    # 7. Backups (presence of a backup tool only)
    tools = [t for t in ("restic", "borg", "rsnapshot", "duplicity", "rclone", "timeshift", "bacula-fd", "duplicati-cli", "kopia") if shutil.which(t)]
    cron_txt = " ".join(filter(None, [read("/etc/crontab")] + [read(os.path.join("/etc/cron.d", f)) for f in (os.listdir("/etc/cron.d") if os.path.isdir("/etc/cron.d") else [])]))
    if not tools and "backup" not in cron_txt.lower():
        add("backups", "No backup tool or backup schedule was found on this server", 5.5, "backups",
            looked_for="restic, borg, rsnapshot, duplicity, rclone, timeshift, bacula, kopia, cron jobs named backup",
            note="If backups are made elsewhere (for example by your hosting provider), confirm they are tested and mark this as not applicable.")

    # 8. Security logs (read-only digest)
    digest = None
    if logs:
        digest = read_logs()
        if digest is None:
            skipped.append("security logs (run with sudo, or add your user to the 'adm' group)")
        else:
            add_log_findings(add, digest, net_expo if socks.get(22) else "internal", "svc:22" if 22 in socks else "host", "root")

    return {"agent_version": VERSION, "agent_id": agent_id(), "hostname": socket.gethostname(), "os": os_name,
            "ip": ", ".join(ips[:4]), "public_ip": public, "as_root": as_root,
            "checked_at": int(time.time()), "services": services, "findings": findings, "skipped": skipped,
            "logs": digest}


# ---------- other devices on the network (read-only) ----------
def default_gateway():
    if os.name == "nt":
        out = ps("(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1).NextHop", 20)
        return out.strip() or None
    code, out = run(["ip", "route", "show", "default"], 5)
    m = re.search(r"default via (\S+)", out or "")
    if m:
        return m.group(1)
    code, out = run(["route", "-n", "get", "default"], 5)        # macOS
    m = re.search(r"gateway:\s*(\S+)", out or "")
    return m.group(1) if m else None


def neighbours():
    """Devices this machine has recently talked to on the local network (its ARP / neighbour table)."""
    found = {}
    code, out = run(["ip", "neigh"], 5)
    for line in (out or "").splitlines():
        m = re.match(r"(\d+\.\d+\.\d+\.\d+) .*lladdr ([0-9a-f:]{17})", line, re.I)
        if m and "FAILED" not in line:
            found[m.group(1)] = m.group(2).lower()
    if not found:
        code, out = run(["arp", "-a"], 10)                         # Windows / macOS
        for line in (out or "").splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\)?\s+(?:at\s+)?([0-9a-f]{1,2}(?:[:-][0-9a-f]{1,2}){5})", line, re.I)
            if m:
                found[m.group(1)] = m.group(2).lower().replace("-", ":")
    out = []
    for ip, mac in found.items():
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_private and not a.is_multicast and not ip.endswith(".255") and mac not in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
            out.append({"ip": ip, "mac": mac})
    return sorted(out, key=lambda d: tuple(int(x) for x in d["ip"].split(".")))[:60]


def port_open(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def add_network_findings(report):
    """Adds what this machine can see of its local network. Read-only; contacts only the router."""
    findings = report["findings"]

    def add(fid, title, severity, category, **details):
        details["category"] = category
        findings.append({"id": fid, "title": title, "severity": severity, "exposure": "network", "asset": "host", "details": details})
    gw = default_gateway()
    devs = neighbours()
    mine = set(str(report.get("ip", "")).replace(" ", "").split(","))
    others = [d for d in devs if d["ip"] != gw and d["ip"] not in mine]
    report["network"] = {"gateway": gw, "devices": others[:60]}
    if gw:
        try:
            private_gw = ipaddress.ip_address(gw).is_private
        except ValueError:
            private_gw = False
        if private_gw:
            if port_open(gw, 23):
                add("router-telnet", f"Your router ({gw}) accepts Telnet logins, which are sent unencrypted", 7.5, "encryption",
                    device=gw, port=23, risk="anyone on your Wi-Fi can read the router password and take over the network",
                    how="Turn off Telnet in the router's admin page (often under Administration or Remote management). Ask your internet provider if you can't find it.")
            if port_open(gw, 21):
                add("router-ftp", f"Your router ({gw}) has unencrypted file sharing (FTP) turned on", 6.0, "encryption",
                    device=gw, port=21, risk="files and the FTP password travel unencrypted on your network")
    if len(others) >= 3:
        add("unchecked-devices", f"{len(others)} other devices on your network are not being checked", 3.5, "segmentation",
            devices=[d["ip"] for d in others[:20]],
            risk="printers, cameras, phones and smart TVs share this network; one weak device can be used to reach the rest",
            how="Install the checker on the computers you own. Put cameras, smart TVs and guest phones on a separate guest Wi-Fi.",
            note="Seen in this computer's recent network table; devices that haven't talked to it recently are not listed.")
    return report


# ---------- macOS ----------
def check_macos(as_root, logs=True):
    ver = platform.mac_ver()[0] or platform.release()
    os_name = f"macOS {ver}"
    ips = [i for i in ip_addresses() if ":" not in i] or ip_addresses()
    public = has_public_ip(ips)
    net_expo = "internet" if public else "network"
    findings, services, skipped = [], [], []

    def add(fid, title, severity, category, exposure="internal", asset="host", **details):
        details["category"] = category
        findings.append({"id": fid, "title": title, "severity": severity, "exposure": exposure, "asset": asset, "details": details})

    socks = listeners()
    code, txt = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], 15)
    for line in (txt or "").splitlines()[1:]:
        m = re.search(r"\s(\S+):(\d+) \(LISTEN\)", line)
        if m:
            p = int(m.group(2))
            socks[p] = socks.get(p, False) or not (m.group(1).startswith("127.") or m.group(1) in ("[::1]", "localhost"))
    for p, exposed in sorted(socks.items()):
        name, group, sev, cat, why = PORTS.get(p, (f"Service on port {p}", "other", 4.0, "misconfig",
                                                     "an unidentified service; check what it is and whether it is needed"))
        services.append({"port": p, "name": name, "cat": group, "exposed": bool(exposed)})
        if exposed and p in PORTS and p not in EXPECTED_WEB:
            add(f"port{p}", f"{name} is open to the network (port {p})", sev, cat, net_expo, f"svc:{p}", port=p, risk=why,
                how="System Settings > General > Sharing: turn off what you don't use")

    code, out = run(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"], 10)
    if out and "enabled" not in out.lower():
        add("firewall", "The macOS firewall is turned off", 5.5 if any(socks.values()) else 4.0, "misconfig", net_expo,
            how="System Settings > Network > Firewall > turn on")
    elif not out:
        skipped.append("firewall state")
    code, out = run(["fdesetup", "status"], 10)
    if out and "FileVault is Off" in out:
        add("disk-encryption", "The disk is not encrypted (FileVault is off)", 6.5, "encryption",
            risk="if this Mac is lost or stolen, its files can be read", how="System Settings > Privacy & Security > FileVault > Turn On")
    code, out = run(["spctl", "--status"], 10)
    if out and "disabled" in out:
        add("gatekeeper", "Gatekeeper is off, so unverified apps can run without warning", 6.0, "thirdparty",
            how="Run 'sudo spctl --master-enable' or ask your IT person")
    code, out = run(["csrutil", "status"], 10)
    if out and "disabled" in out.lower():
        add("sip", "System Integrity Protection is turned off", 7.0, "misconfig",
            risk="malware can change protected parts of macOS", how="Needs Recovery Mode; ask your IT person to turn it back on")
    code, out = run(["softwareupdate", "-l"], 150)
    labels = re.findall(r"\* Label: (.+)", out or "")
    if labels:
        sec = [l for l in labels if re.search(r"security|macos|background|xprotect|rapid", l, re.I)]
        add("sec-updates" if sec else "updates", f"{len(labels)} macOS update(s) are waiting to be installed",
            7.5 if sec else 5.0, "patches" if sec else "outdated", affected_software=labels[:15],
            how="System Settings > General > Software Update")
    elif code is None:
        skipped.append("pending updates")
    code, out = run(["defaults", "read", "/Library/Preferences/com.apple.SoftwareUpdate", "CriticalUpdateInstall"], 10)
    if out.strip() == "0":
        add("auto-updates", "Automatic security responses and system files are turned off", 4.5, "outdated",
            how="System Settings > General > Software Update > Automatic updates (i) > turn on 'Install Security Responses and system files'")
    try:
        major = int(ver.split(".")[0])
        if major < 14:
            add("os-eol", f"Unsupported OS: {os_name} no longer receives regular security updates", 8.0, "unsupporteddev",
                reason="Apple usually patches only the three newest macOS versions", note="Based on Apple's usual support pattern.")
    except ValueError:
        pass
    code, out = run(["dscl", ".", "-read", "/Groups/admin", "GroupMembership"], 10)
    admins = [a for a in (out or "").replace("GroupMembership:", "").split() if a not in ("root",)]
    if len(admins) > 3:
        add("admins", f"{len(admins)} people can act as administrator", 4.0, "excessive", count=len(admins))
    code, out = run(["tmutil", "latestbackup"], 15)
    if code not in (0, None) or not (out or "").strip():
        add("backups", "No recent Time Machine backup was found", 5.5, "backups",
            note="If you back up another way (for example iCloud Drive or a backup app), mark this as not applicable.",
            how="System Settings > General > Time Machine > Add Backup Disk")
    if logs:
        skipped.append("security logs (not read on macOS yet)")
    return {"agent_version": VERSION, "agent_id": agent_id(), "hostname": socket.gethostname(), "os": os_name,
            "ip": ", ".join(ips[:4]), "public_ip": public, "as_root": as_root,
            "checked_at": int(time.time()), "services": services, "findings": findings, "skipped": skipped, "logs": None}


def full_check(as_root, logs=True, network=True):
    if os.name == "nt":
        rep = check_windows(as_root, logs)
    elif sys.platform == "darwin":
        rep = check_macos(as_root, logs)
    else:
        rep = check(as_root, logs)
    if network:
        try:
            add_network_findings(rep)
        except Exception:
            rep["skipped"].append("network devices")
    return rep


def poll(server, token, aid):
    req = urllib.request.Request(server.rstrip("/") + "/api/agent/poll", data=json.dumps({"agent_id": aid}).encode(),
                                 headers={"Content-Type": "application/json", "X-Enroll-Token": token}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return bool(json.loads(r.read()).get("scan"))


def watch(server, token, as_root, logs, quiet, network=True, every=6.0):
    """Stay running: re-check when someone presses 'Scan now' on the dashboard, and every few hours."""
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))
    aid, last_full, fails = agent_id(), time.time(), 0
    say("Listening for 'Scan now' from your dashboard. Close this window or press Ctrl+C to stop.")
    while True:
        try:
            want = poll(server, token, aid)
            fails = 0
            if want or time.time() - last_full > every * 3600:
                say(time.strftime("%H:%M") + "  " + ("Scan requested from the dashboard. Checking…" if want else "Scheduled check…"))
                rep = full_check(as_root, logs=logs, network=network); rep["watch"] = True
                send(server, token, rep)
                last_full = time.time()
                say(time.strftime("%H:%M") + f"  Sent: {len(rep['findings'])} problem(s) found.")
            time.sleep(15)
        except KeyboardInterrupt:
            say("Stopped."); return
        except urllib.error.HTTPError as e:
            if e.code == 403:
                say("The dashboard no longer accepts this access code (it was reset or the server was removed). Stopping.")
                return
            fails += 1; time.sleep(min(300, 15 * fails))
        except Exception:
            fails += 1; time.sleep(min(300, 15 * fails))


def send(server, token, report):
    req = urllib.request.Request(server.rstrip("/") + "/api/agent/report", data=json.dumps(report).encode(),
                                 headers={"Content-Type": "application/json", "X-Enroll-Token": token}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def install(server, token, watch_mode=False):
    if os.name == "nt":
        return install_windows(server, token, watch_mode)
    if watch_mode:
        return install_linux_watch(server, token)
    os.makedirs(HOME_DIR, exist_ok=True)
    target = os.path.join(HOME_DIR, "agent.py")
    shutil.copyfile(os.path.abspath(__file__), target)
    cfg = os.path.join(HOME_DIR, "config.json")
    with open(cfg, "w") as f:
        json.dump({"server": server, "token": token}, f)
    os.chmod(cfg, 0o600)
    if not shutil.which("crontab"):
        print(f"Saved to {HOME_DIR}. 'crontab' is not available, so schedule this yourself:\n  python3 {target} --config {cfg} --quiet")
        return
    code, cur = run(["crontab", "-l"], 10)
    lines = [l for l in (cur or "").splitlines() if "infrasentinel/agent.py" not in l]
    minute = int(hashlib.sha256(socket.gethostname().encode()).hexdigest(), 16) % 60
    lines.append(f"{minute} */6 * * * {sys.executable} {target} --config {cfg} --quiet >/dev/null 2>&1")
    p = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, capture_output=True)
    if p.returncode == 0:
        print(f"Installed: {target}\nIt will re-check this server every 6 hours (cron for user '{os.environ.get('USER', '?')}').\n"
              f"To remove it later:  python3 {target} --uninstall")
    else:
        print("Could not add the schedule:", p.stderr.strip())


def install_linux_watch(server, token):
    os.makedirs(HOME_DIR, exist_ok=True)
    target = os.path.join(HOME_DIR, "agent.py")
    shutil.copyfile(os.path.abspath(__file__), target)
    cfg = os.path.join(HOME_DIR, "config.json")
    with open(cfg, "w") as f:
        json.dump({"server": server, "token": token}, f)
    os.chmod(cfg, 0o600)
    cmdline = f"{sys.executable} {target} --config {cfg} --watch --quiet"
    if shutil.which("crontab"):
        code, cur = run(["crontab", "-l"], 10)
        lines = [l for l in (cur or "").splitlines() if "infrasentinel/agent.py" not in l]
        lines.append(f"@reboot {cmdline} >/dev/null 2>&1")
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, capture_output=True)
    subprocess.Popen(cmdline.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(f"Installed: {target}\nIt is running in the background now and starts again after a reboot, so the dashboard can scan this machine any time.\n"
          f"To remove it:  python3 {target} --uninstall   (then restart, or stop the running copy with: pkill -f infrasentinel/agent.py)")


def install_windows(server, token, watch_mode=False):
    os.makedirs(HOME_DIR, exist_ok=True)
    frozen = getattr(sys, "frozen", False)          # running as the ready-made infrasentinel-agent.exe
    target = os.path.join(HOME_DIR, "infrasentinel-agent.exe" if frozen else "agent.py")
    shutil.copyfile(sys.executable if frozen else os.path.abspath(__file__), target)
    cfg = os.path.join(HOME_DIR, "config.json")
    with open(cfg, "w") as f:
        json.dump({"server": server, "token": token}, f)
    py = sys.executable.replace("python.exe", "pythonw.exe") if os.path.exists(sys.executable.replace("python.exe", "pythonw.exe")) else sys.executable
    if watch_mode:
        tr = (f'"{target}"' if frozen else f'"{py}" "{target}"') + f' --config "{cfg}" --watch --quiet'
        code, out = run(["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", "InfraSentinelAgent", "/TR", tr], 30)
        if code == 0:
            run(["schtasks", "/Run", "/TN", "InfraSentinelAgent"], 30)
            print(f"Installed: {target}\nIt is running in the background now and starts again whenever you sign in to Windows,\n"
                  f"so the dashboard can scan this PC any time.\nTo remove it:  " + (f'"{target}"' if frozen else f'python "{target}"') + " --uninstall")
        else:
            print("Could not add the scheduled task (try a Terminal opened as administrator). You can keep this window open instead.")
        return
    tr = (f'"{target}"' if frozen else f'"{py}" "{target}"') + f' --config "{cfg}" --quiet'
    code, out = run(["schtasks", "/Create", "/F", "/SC", "HOURLY", "/MO", "6", "/TN", "InfraSentinelAgent", "/TR", tr], 30)
    if code == 0:
        print(f"Installed: {target}\nIt will re-check this PC every 6 hours (Task Scheduler: InfraSentinelAgent).\n"
              f'To remove it later:  python "{target}" --uninstall')
    else:
        print("Could not add the scheduled task. You can run the command again later instead.")


def uninstall():
    if os.name == "nt":
        run(["schtasks", "/End", "/TN", "InfraSentinelAgent"], 30)
        run(["schtasks", "/Delete", "/F", "/TN", "InfraSentinelAgent"], 30)
        shutil.rmtree(HOME_DIR, ignore_errors=True)
        print("Removed the InfraSentinel scheduled task and files from this PC.")
        return
    if shutil.which("crontab"):
        code, cur = run(["crontab", "-l"], 10)
        lines = [l for l in (cur or "").splitlines() if "infrasentinel/agent.py" not in l]
        subprocess.run(["crontab", "-"], input="\n".join(lines) + ("\n" if lines else ""), text=True, capture_output=True)
    shutil.rmtree(HOME_DIR, ignore_errors=True)
    print("Removed the InfraSentinel schedule and files from this server.")


def main():
    ap = argparse.ArgumentParser(description="InfraSentinel read-only server checks")
    ap.add_argument("--server"); ap.add_argument("--token"); ap.add_argument("--config")
    ap.add_argument("--install", action="store_true"); ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-logs", action="store_true", help="do not read or send any log information")
    ap.add_argument("--watch", action="store_true", help="keep running so the dashboard can request a scan ('Scan now')")
    ap.add_argument("--every", type=float, default=6.0, help="with --watch: hours between automatic full checks (default 6)")
    ap.add_argument("--no-network", action="store_true", help="do not look at other devices on the network or contact the router")
    a = ap.parse_args()
    if a.uninstall:
        return uninstall()
    if a.config:
        cfg = json.load(open(a.config))
        a.server, a.token = a.server or cfg.get("server"), a.token or cfg.get("token")
    as_root = is_admin()
    if not a.quiet:
        print(f"InfraSentinel agent {VERSION}: checking {socket.gethostname()} (read-only)…")
    report = full_check(as_root, logs=not a.no_logs, network=not a.no_network)
    if a.watch:
        report["watch"] = True
    if a.dry_run:
        print(json.dumps(report, indent=2))
        return
    if not a.server or not a.token:
        sys.exit("Missing --server and --token. Copy the full command from your InfraSentinel dashboard.")
    try:
        send(a.server, a.token, report)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except Exception:
            msg = str(e)
        sys.exit(f"The dashboard refused the report: {msg}")
    except Exception as e:
        sys.exit(f"Could not reach the dashboard at {a.server}: {e}\nCheck the address. For a machine elsewhere, start InfraSentinel with --public (or --lan on the same network) and copy the command again.")
    if not a.quiet:
        n = len(report["findings"])
        print(f"Done. Checked {len(report['services'])} services and the system settings; found {n} problem{'s' if n != 1 else ''}.")
        if report["skipped"]:
            print("Skipped: " + "; ".join(report["skipped"]))
        print(f"See the results and simple fixes on your dashboard: {a.server.rstrip('/')}/")
    if a.install:
        install(a.server, a.token, a.watch)
    elif a.watch:
        watch(a.server, a.token, as_root, not a.no_logs, a.quiet, not a.no_network, max(0.25, a.every))


if __name__ == "__main__":
    main()
