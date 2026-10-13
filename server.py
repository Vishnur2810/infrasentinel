#!/usr/bin/env python3
"""InfraSentinel local server.

- Accounts: organizations sign in to their own dashboard (hashed passwords, session cookie).
- Connect a server: the client runs a one-line command on a server THEY own. It downloads
  agent.py, which performs read-only checks and reports back with the organization's
  enrollment token. Nothing on the client's server is changed.
- Serves the console, the synthetic demo organizations, a live check of this laptop,
  and plain-language explanations from a local Ollama model.

Standard library only.  Run:  python3 server.py          (this laptop only)
                              python3 server.py --lan    (let other machines on your network connect)
"""
import hashlib, hmac, json, os, re, secrets, socket, subprocess, sys, time, urllib.request, webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie

LAN = "--lan" in sys.argv or os.environ.get("IS_BIND") == "0.0.0.0"
PUBLIC_URL = os.environ.get("IS_PUBLIC_URL", "").strip().rstrip("/")   # set by start.sh --public (Cloudflare tunnel)
AI_LIMIT = (20, 600)                                                   # public mode: 20 AI requests per account per 10 min
AI_USE = {}
HOST = "0.0.0.0" if LAN else "127.0.0.1"
PORT = int(os.environ.get("IS_PORT", "8765"))
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
SEC_MODEL = "hf.co/mradermacher/Foundation-Sec-8B-Instruct-GGUF:Q4_K_M"
# Preference order when no model has been chosen in the app (matched case-insensitively as a substring).
PREFERRED = [os.environ.get("IS_MODEL", ""), "foundation-sec", "llama3.1:8b", "llama3.1", "gemma3", "mistral",
             "llama3.2", "phi4"]
RECOMMENDED = [
    {"name": SEC_MODEL, "label": "Foundation-Sec 8B (Cisco, security-tuned)", "size": "about 5 GB"},
    {"name": "llama3.1:8b", "label": "Llama 3.1 8B (general purpose)", "size": "about 4.9 GB"},
    {"name": "llama3.2:3b", "label": "Llama 3.2 3B (small and fast)", "size": "about 2 GB"},
]
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ORGS_FILE = os.path.join(DATA, "organizations.json")    # synthetic demo organizations
USERS_FILE = os.path.join(DATA, "users.json")           # accounts
ACCOUNTS_FILE = os.path.join(DATA, "accounts.json")     # client organizations + enrollment tokens
HOSTS_DIR = os.path.join(DATA, "hosts")                 # agent reports, one file per account
SESSION_TTL = 12 * 3600
SESSIONS = {}                                           # token -> (email, expiry)
MAX_REPORT = 1_000_000


# ---------- small JSON store ----------
def jload(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def jsave(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def load_orgs():
    return jload(ORGS_FILE, {})


def state_file(acct):
    return os.path.join(DATA, f"remediation_{acct}.json")


# ---------- accounts ----------
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt, hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "org"


def create_account(org_name, org_type, email, pw):
    users, accts = jload(USERS_FILE, {}), jload(ACCOUNTS_FILE, {})
    email = email.strip().lower()
    if email in users:
        raise ValueError("An account with this email already exists. Sign in instead.")
    if len(pw) < 8:
        raise ValueError("Use a password of at least 8 characters.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("Enter a valid email address.")
    acct = slug(org_name)
    while acct in accts:
        acct += "-" + secrets.token_hex(2)
    accts[acct] = {"name": org_name.strip()[:80], "type": org_type, "token": secrets.token_urlsafe(18),
                   "created": int(time.time())}
    salt, h = hash_pw(pw)
    users[email] = {"acct": acct, "salt": salt, "hash": h, "created": int(time.time())}
    jsave(ACCOUNTS_FILE, accts)
    jsave(USERS_FILE, users)
    return email


def check_login(email, pw):
    u = jload(USERS_FILE, {}).get(email.strip().lower())
    if not u:
        return None
    _, h = hash_pw(pw, u["salt"])
    return email.strip().lower() if hmac.compare_digest(h, u["hash"]) else None


def ensure_demo():
    if not jload(USERS_FILE, {}):
        create_account("Demo Organization", "college", "demo@example.com", "demo1234")
        return True
    return False


def acct_by_token(token):
    for k, v in jload(ACCOUNTS_FILE, {}).items():
        if token and hmac.compare_digest(v.get("token", ""), token):
            return k
    return None


# ---------- live check of this laptop (unchanged) ----------
PORTS = {
    21: ("FTP server", "file", 7.5, "FTP sends passwords and files unencrypted"),
    22: ("SSH remote login", "remote", 5.3, "remote shell login is open; brute-force target if passwords are allowed"),
    23: ("Telnet", "remote", 9.0, "Telnet sends logins in clear text and is obsolete"),
    25: ("SMTP mail server", "web", 5.0, "a mail server can be abused as an open relay if misconfigured"),
    53: ("DNS resolver", "other", 4.0, "a DNS service can be abused for amplification if exposed"),
    80: ("HTTP web server", "web", 5.0, "a web service without HTTPS exposes traffic in clear text"),
    111: ("RPC portmapper", "file", 5.0, "rpcbind reveals RPC services and has been used in DDoS amplification"),
    139: ("NetBIOS / SMB", "file", 7.5, "Windows-style file sharing is a common lateral-movement target"),
    443: ("HTTPS web server", "web", 3.0, "an encrypted web service; risk depends on the app behind it"),
    445: ("SMB file sharing", "file", 7.5, "SMB file sharing is a common ransomware entry and spread path"),
    631: ("CUPS printing", "other", 4.3, "the print service has had remote-code-execution bugs (2024)"),
    1433: ("Microsoft SQL Server", "data", 7.0, "a database accepting network connections"),
    1883: ("MQTT broker", "data", 6.5, "IoT message broker often runs without authentication"),
    2375: ("Docker API (no TLS)", "remote", 9.8, "unauthenticated Docker API gives full control of the machine"),
    3000: ("Dev web server", "web", 5.0, "a development server, usually not hardened for exposure"),
    3306: ("MySQL / MariaDB", "data", 7.0, "a database accepting network connections"),
    3389: ("Remote Desktop", "remote", 8.1, "remote desktop is a top ransomware entry point"),
    5000: ("Dev web server", "web", 5.0, "a development server, usually not hardened for exposure"),
    5173: ("Vite dev server", "web", 4.5, "a frontend dev server that can leak source files"),
    5432: ("PostgreSQL", "data", 7.0, "a database accepting network connections"),
    5900: ("VNC remote desktop", "remote", 8.0, "VNC is often weakly protected remote screen control"),
    6379: ("Redis", "data", 8.5, "Redis has no password by default and can be abused to run commands"),
    8000: ("Web app / dev server", "web", 5.0, "a web or development server"),
    8080: ("Web app / proxy", "web", 5.0, "a web application or proxy"),
    8888: ("Jupyter notebook", "remote", 7.5, "Jupyter can run arbitrary code if its token leaks or is disabled"),
    9200: ("Elasticsearch", "data", 8.0, "search database that has caused many data leaks when exposed"),
    11434: ("Ollama AI API", "data", 6.5, "the local AI API has no authentication by default"),
    27017: ("MongoDB", "data", 8.0, "database that has caused many data leaks when exposed"),
}
CATS = {"remote": ("Remote access", 85), "file": ("File sharing", 75), "data": ("Data & databases", 90),
        "web": ("Web apps & sites", 60), "other": ("System services", 45), "ops": ("Server operations", 70)}


def listening_sockets():
    out = {}
    try:
        txt = subprocess.run(["ss", "-H", "-tln"], capture_output=True, text=True, timeout=5).stdout
        for line in txt.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            addr, _, port = parts[3].rpartition(":")
            if not port.isdigit():
                continue
            addr = addr.strip("[]").split("%")[0]
            local_only = addr.startswith("127.") or addr == "::1"
            p = int(port)
            out[p] = out.get(p, False) or not local_only
        if out:
            return out, "ss (socket table)"
    except Exception:
        pass

    def probe(p):
        with socket.socket() as s:
            s.settimeout(0.3)
            return p if s.connect_ex(("127.0.0.1", p)) == 0 else None
    with ThreadPoolExecutor(64) as ex:
        found = [p for p in ex.map(probe, PORTS) if p]
    return {p: None for p in found}, "localhost connect scan"


def ssh_password_auth():
    try:
        txt = open("/etc/ssh/sshd_config").read()
        m = re.findall(r"^\s*PasswordAuthentication\s+(\w+)", txt, re.M | re.I)
        return m[0].lower() if m else "default (yes)"
    except Exception:
        return None


def scan():
    socks, method = listening_sockets()
    socks.pop(PORT, None)
    host = socket.gethostname()
    nodes = [["host", f"{host} (this laptop)", 0, 80]]
    edges, findings, cats_used = [], [], set()
    for p, exposed in sorted(socks.items()):
        name, cat, sev, why = PORTS.get(p, (f"Unknown service :{p}", "other", 4.0,
                                           "an unidentified service; confirm what it is and whether it is needed"))
        nid = f"p{p}"
        nodes.append([nid, f"{name} :{p}", 1, CATS[cat][1]])
        edges += [["host", nid], [nid, "c_" + cat]]
        cats_used.add(cat)
        if exposed is None:
            expo, where = "unknown", "exposure unknown"
        elif exposed:
            expo, where = "network", "listening on all network interfaces"
        else:
            expo, where = "isolated", "bound to localhost only"
            sev = round(sev * 0.6, 1)
        findings.append([f"f{p}", f"{name} on port {p}, {where}", nid, sev, expo, f"Live scan · {method}",
                         {"port": p, "service": name, "risk": why, "binding": where}])
    pa = ssh_password_auth()
    if 22 in socks and pa and pa.startswith(("yes", "default")):
        findings.append(["fsshpw", "SSH allows password logins", "p22", 7.0,
                         "network" if socks.get(22) else "isolated", "Live scan · sshd_config",
                         {"setting": f"PasswordAuthentication {pa}", "risk": "password guessing against SSH"}])
    for c in sorted(cats_used):
        nodes.append(["c_" + c, CATS[c][0], 2, CATS[c][1], 1])
    return {"label": "This laptop (live)", "org": f"Live scan of {host} · {len(socks)} listening services · method: {method}",
            "nodes": nodes, "edges": edges, "findings": findings,
            "owners": ["You (device owner)", "Team member", "IT admin"]}


# ---------- connected servers (agent reports) ----------
def hosts_file(acct):
    return os.path.join(HOSTS_DIR, f"{acct}.json")


HOSTS_LOCK = __import__("threading").Lock()


def host_id(agent_id):
    return re.sub(r"[^a-zA-Z0-9_-]", "", str(agent_id or ""))[:32]


def save_report(acct, rep):
    hid = host_id(rep.get("agent_id")) or secrets.token_hex(6)
    with HOSTS_LOCK:
        hosts = jload(hosts_file(acct), {})
        rep["received_at"] = rep["last_seen"] = int(time.time())
        hosts[hid] = rep                    # a new report also clears any pending "Scan now" request
        jsave(hosts_file(acct), hosts)
    return hid


def agent_poll(acct, agent_id):
    """A watching agent checks in. Returns True when someone pressed 'Scan now' for it."""
    hid = host_id(agent_id)
    with HOSTS_LOCK:
        hosts = jload(hosts_file(acct), {})
        h = hosts.get(hid)
        if not h:
            return False
        h["last_seen"] = int(time.time())
        h["watch"] = True
        want = bool(h.get("scan_requested"))
        jsave(hosts_file(acct), hosts)
    return want


def request_scan(acct, hid):
    with HOSTS_LOCK:
        hosts = jload(hosts_file(acct), {})
        h = hosts.get(str(hid))
        if not h:
            raise ValueError("That server is no longer connected.")
        if not h.get("watch") or time.time() - h.get("last_seen", 0) > 90:
            raise ValueError("That machine isn't listening right now. Start the checker on it with the 'Scan now' option, then try again.")
        h["scan_requested"] = int(time.time())
        jsave(hosts_file(acct), hosts)


def hosts_sector(acct, name):
    """Turn every connected server's latest report into one dashboard 'organization'."""
    hosts = jload(hosts_file(acct), {})
    if not hosts:
        return None, []
    nodes, edges, findings, cats, summary = [], [], [], set(), []
    for hid, r in sorted(hosts.items(), key=lambda kv: kv[1].get("hostname", "")):
        hn = str(r.get("hostname", hid))[:60]
        hnode = f"h_{hid}"
        nodes.append([hnode, hn, 0, 80])
        edges.append([hnode, "c_ops"])
        cats.add("ops")
        for s in r.get("services", [])[:40]:
            try:
                port = int(s.get("port"))
            except Exception:
                continue
            cat = s.get("cat") if s.get("cat") in CATS else "other"
            snode = f"{hnode}_p{port}"
            nm = str(s.get('name', 'Service'))[:40]
            nm = f"Port {port} service" if nm.lower().startswith("service on port") else f"{nm} ({port})"
            nodes.append([snode, nm + (f" · {hn.replace(' (this laptop)', '')}" if len(hosts) > 1 else ""), 1, CATS[cat][1]])
            edges += [[hnode, snode], [snode, "c_" + cat]]
            cats.add(cat)
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in r.get("findings", [])[:100]:
            asset = f.get("asset", "host")
            anode = f"{hnode}_p{asset[4:]}" if str(asset).startswith("svc:") else hnode
            if not any(n[0] == anode for n in nodes):
                anode = hnode
            try:
                sev = max(0.0, min(10.0, float(f.get("severity", 5))))
            except Exception:
                sev = 5.0
            expo = f.get("exposure") if f.get("exposure") in ("internet", "network", "internal", "isolated", "unknown") else "unknown"
            title = str(f.get('title', 'Finding'))[:140] + (f" ({hn})" if len(hosts) > 1 else "")
            findings.append([f"f_{hid}_{str(f.get('id', len(findings)))[:40]}", title,
                             anode, sev, expo, "Checker", f.get("details") or {}])
        lg = r.get("logs") if isinstance(r.get("logs"), dict) else None
        summary.append({"id": hid, "hostname": hn, "os": str(r.get("os", ""))[:80], "ip": str(r.get("ip", ""))[:45],
                        "checked_at": r.get("checked_at"), "received_at": r.get("received_at"),
                        "as_root": bool(r.get("as_root")), "findings": len(r.get("findings", [])),
                        "skipped": r.get("skipped", [])[:10], "agent_version": r.get("agent_version"),
                        "online": bool(r.get("watch")) and time.time() - r.get("last_seen", 0) < 90,
                        "scan_requested": bool(r.get("scan_requested")),
                        "logs": {k: lg.get(k) for k in ("source", "failed_logins", "root_logins", "sudo_failures",
                                                         "system_errors_24h", "lines_read")} | {"new_users": len(lg.get("new_users") or [])} if lg else None})
    for c in sorted(cats):
        nodes.append(["c_" + c, CATS[c][0], 2, CATS[c][1], 1])
    sector = {"label": "My servers", "org": f"{name} · {len(hosts)} connected server{'s' if len(hosts) != 1 else ''} · checked by the InfraSentinel agent",
              "nodes": nodes, "edges": edges, "findings": findings,
              "owners": ["Server admin", "IT person", "Hosting provider"]}
    return sector, summary


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packets are sent
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# ---------- local AI ----------
def ollama(path, payload=None, timeout=5):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(payload).encode() if payload else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


SETTINGS_FILE = os.path.join(DATA, "settings.json")


def installed_models():
    return [m["name"] for m in ollama("/api/tags").get("models", [])]


def pick_model():
    names = installed_models()
    chosen = jload(SETTINGS_FILE, {}).get("model")
    if chosen in names:
        return chosen
    for want in PREFERRED:
        if not want:
            continue
        for n in names:
            if want.lower() in n.lower():
                return n
    return names[0] if names else None


AI_OFF = "The AI helper isn't running. Start it with 'ollama serve' (or restart with 'bash start.sh'), then try again."
AI_NOMODEL = "No AI model is downloaded yet. Run 'bash start.sh' (it downloads the security model, about 5 GB), then try again."


def ai_model():
    try:
        m = pick_model()
    except Exception:
        raise RuntimeError(AI_OFF)
    if not m:
        raise RuntimeError(AI_NOMODEL)
    return m


NUM_CTX = int(os.environ.get("IS_CTX", "12288"))   # memory window: big enough for scan data + logs + answer
SYSTEM_PROMPT = (
    "You are InfraSentinel's security assistant for a small organization (business, school, college or clinic) "
    "whose owner is NOT a computer expert.\n"
    "- Answer in clear, everyday language. Use short paragraphs, and numbered steps for instructions. Give complete answers; don't stop half-way.\n"
    "- For facts about THEIR systems, use only the scan and log data provided. If the data doesn't say, say so and explain how they could check.\n"
    "- You may use general security knowledge to explain ideas and give how-to steps for common systems such as Ubuntu.\n"
    "- Never invent findings, numbers, IP addresses, CVEs or software versions.\n"
    "- When something is serious or risky to fix alone (signs of a break-in, critical problems, changes that could lock them out), "
    "clearly recommend contacting a security professional, and say what to do meanwhile.\n"
    "- Only help with protecting systems they own. Do not give instructions for attacking other systems.\n"
    "- Formatting: use short labelled sections (for example 'What's wrong:'), numbered steps, and paragraphs of 1-3 sentences. "
    "Put every command in its own fenced code block with a language (```bash or ```powershell), one command per line, "
    "with no prompt symbols like $ or >. Never put commands inside a sentence. Do not use tables.")


def generate(model, prompt, max_tokens):
    try:
        r = ollama("/api/generate", {"model": model, "prompt": prompt, "stream": False,
                                     "options": {"temperature": 0.2, "num_predict": max_tokens, "num_ctx": NUM_CTX}}, timeout=300)
    except Exception:
        raise RuntimeError("The AI helper took too long or stopped. Try again in a moment.")
    return r.get("response", "").strip()


def scan_context(acct):
    """Compact description of the account's connected servers, for grounding chat answers."""
    hosts = jload(hosts_file(acct), {})
    if not hosts:
        return "No servers have been scanned yet."
    out = []
    for hid, r in hosts.items():
        lg = r.get("logs") or {}
        out.append({
            "server": r.get("hostname"), "os": r.get("os"), "checked_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("checked_at", 0))),
            "open_to_network": [f"{s.get('name')} (port {s.get('port')})" for s in r.get("services", []) if s.get("exposed")][:15],
            "problems": [{"title": f.get("title"), "severity_0_10": f.get("severity"), "category": (f.get("details") or {}).get("category"),
                          "details": {k: v for k, v in (f.get("details") or {}).items() if k not in ("category",)}}
                         for f in r.get("findings", [])][:30],
            "logs": {k: lg.get(k) for k in ("source", "failed_logins", "top_source_ips", "usernames_tried", "accepted_logins",
                                             "accepted_by_user", "root_logins", "sudo_failures", "new_users",
                                             "system_errors_24h", "top_system_errors")} if lg else "not readable",
            "checks_skipped": r.get("skipped", [])})
    return json.dumps(out, indent=1)[:12000]


# ---------- web research (public pages only) ----------
import html as _html, ipaddress, urllib.parse, urllib.error
from html.parser import HTMLParser

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
TRUSTED = ("ubuntu.com", "askubuntu.com", "debian.org", "redhat.com", "archlinux.org", "digitalocean.com", "man7.org",
           "nist.gov", "cisa.gov", "owasp.org", "openssh.com", "postgresql.org", "mysql.com", "docker.com", "microsoft.com",
           "cloudflare.com", "linuxize.com", "cyberciti.biz", "serverfault.com", "stackexchange.com", "github.com")
STOP = set("the a an and or of to in on for with is are be my your how do does what why can i it this that from into at by as".split())


def _public(url):
    try:
        u = urllib.parse.urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        return all(ipaddress.ip_address(i[4][0]).is_global for i in socket.getaddrinfo(u.hostname, None))
    except Exception:
        return False


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _public(newurl):
            raise urllib.error.URLError("redirect to a non-public address blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


def _get(url, data=None, limit=700_000, timeout=8):
    if not _public(url):
        raise ValueError("not a public address")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                                                          "Accept-Language": "en"})
    with _opener.open(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            raise ValueError("not a web page")
        raw = r.read(limit)
        cs = r.headers.get_content_charset() or "utf-8"
        return raw.decode(cs, "replace")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "button", "select"}
    BLOCK = {"p", "li", "pre", "code", "h1", "h2", "h3", "h4", "td", "dd", "dt", "blockquote", "div", "section", "article", "br", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.parts, self.title, self.in_title = 0, [], "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, d):
        if self.in_title:
            self.title += d
        elif not self.skip:
            self.parts.append(d)


def _best_chunks(text, query, limit=1800):
    words = {w for w in re.findall(r"[a-z0-9_./-]+", query.lower()) if len(w) > 2 and w not in STOP}
    paras = [re.sub(r"[ \t]+", " ", p).strip() for p in text.split("\n")]
    paras = [p for p in paras if len(p) > 35]
    scored = []
    for i, p in enumerate(paras):
        lp = p.lower()
        s = sum(1 for w in words if w in lp)
        if re.search(r"\b(sudo|systemctl|apt|ufw|/etc/|sshd|chmod|passwd|dnf)\b", lp):
            s += 2
        scored.append((s, i, p))
    keep = sorted(sorted(scored, key=lambda x: -x[0])[:14], key=lambda x: x[1])
    out, n = [], 0
    for s, i, p in keep:
        if s == 0 or n + len(p) > limit:
            continue
        out.append(p[:600]); n += len(p[:600])
    return "\n".join(out)


def _ddg(query, n=8):
    data = urllib.parse.urlencode({"q": query, "kl": "wt-wt"}).encode()
    for url in ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/"):
        try:
            page = _get(url, data=data, timeout=8)
        except Exception:
            continue
        found, seen = [], set()
        for m in re.finditer(r"<a\s([^>]*)>(.*?)</a>", page, re.S | re.I):
            attrs, inner = m.group(1), m.group(2)
            h = re.search(r"href\s*=\s*[\"']([^\"']+)", attrs)
            c = re.search(r"class\s*=\s*[\"']([^\"']+)", attrs)
            if not h:
                continue
            href, cls = _html.unescape(h.group(1)), (c.group(1) if c else "")
            if "uddg=" in href:
                target = urllib.parse.parse_qs(urllib.parse.urlparse(href if "://" in href else "https:" + href).query).get("uddg", [None])[0]
            elif ("result__a" in cls or "result-link" in cls) and href.startswith("http"):
                target = href
            else:
                continue
            if not target or "duckduckgo.com" in target or target in seen:
                continue
            seen.add(target)
            found.append({"url": target, "title": _html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()[:140]})
            if len(found) >= n:
                break
        if found:
            return found
    return []


def _ollama_search(query, n=5):
    req = urllib.request.Request("https://ollama.com/api/web_search", data=json.dumps({"query": query, "max_results": n}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {OLLAMA_API_KEY}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()).get("results", [])


def web_research(query, n=3):
    """Search the web and return up to n sources: [{n, title, url, text}]. Never raises."""
    sources = []
    if OLLAMA_API_KEY:
        try:
            for r in _ollama_search(query):
                txt = _best_chunks(str(r.get("content", "")), query) or str(r.get("content", ""))[:1800]
                if len(txt) > 150:
                    sources.append({"title": str(r.get("title") or r.get("url"))[:140], "url": r.get("url"), "text": txt})
                if len(sources) >= n:
                    break
        except Exception:
            sources = []
    if not sources:
        results = _ddg(query)
        results.sort(key=lambda r: 0 if any(d in urllib.parse.urlparse(r["url"]).netloc for d in TRUSTED) else 1)

        def grab(r):
            try:
                p = _Text()
                p.feed(_get(r["url"], timeout=7))
                txt = _best_chunks("".join(p.parts), query)
                return {"title": (p.title.strip() or r["title"] or r["url"])[:140], "url": r["url"], "text": txt} if len(txt) > 200 else None
            except Exception:
                return None
        with ThreadPoolExecutor(5) as ex:
            for s in ex.map(grab, results[:6]):
                if s and len(sources) < n:
                    sources.append(s)
    for i, s in enumerate(sources, 1):
        s["n"] = i
    return sources


def _os_short(acct):
    for r in jload(hosts_file(acct), {}).values():
        m = re.match(r"([A-Za-z]+(?: Linux)?)\s+(\d+(?:\.\d+)?)", str(r.get("os", "")))
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return "Linux"


def web_query(acct, b):
    kind = b.get("kind", "chat")
    osn = _os_short(acct)
    if kind == "explain":
        title = re.sub(r"\s*\([^)]*\)\s*$", "", str((b.get("evidence") or {}).get("problem", "")))
        return f"{title} {osn} how to fix securely"
    if kind == "chat":
        q = str(b.get("question", "")).strip()
        if len(q) < 4 or q.lower() in ("continue", "go on", "more"):
            return None
        return f"{q[:180]} {osn}" if osn.split()[0].lower() not in q.lower() else q[:200]
    return None


def build_messages(acct, b, sources=None):
    """Turn an assistant request into chat messages. kind: chat | explain | summary | logs."""
    kind = b.get("kind", "chat")
    history = [m for m in b.get("history", [])[-8:] if m.get("role") in ("user", "assistant")]
    history = [{"role": m["role"], "content": str(m.get("content", ""))[:4000]} for m in history]
    ctx = scan_context(acct)[: 7000 if sources else 12000]
    sys_msg = {"role": "system", "content": SYSTEM_PROMPT + "\n\nScan data for this organization (JSON):\n" + ctx}
    web = ""
    if sources:
        web = ("\n\nWeb sources found just now (use them for accurate, current fix steps; cite them inline like [1]; "
               "ignore anything unsafe, irrelevant or meant for attacking systems; prefer official documentation when sources disagree):\n" +
               "\n\n".join(f"[{s['n']}] {s['title']} — {s['url']}\n{s['text']}" for s in sources))

    def with_web(q):
        return [sys_msg] + history + [{"role": "user", "content": q + web}]
    if kind == "explain":
        ev = b.get("evidence", {})
        q = ("Explain this one problem for me, using its evidence below.\n"
             "Format:\nWhat's wrong:\nWhy it matters to you:\nWhat to do: (numbered, simple steps; for Ubuntu include the exact menu or command where helpful, "
             "and say how to check it worked)\n"
             "Who should do it: (use the how_hard value)\n"
             "If call_professional is true, end by clearly saying to get a security professional and what to do meanwhile.\n\n"
             "Evidence (JSON):\n" + json.dumps(ev, indent=1)[:5000])
        return with_web(q), 2048
    if kind == "summary":
        items = b.get("problems", [])[:30]
        q = ("Review all the problems found on my servers (list below, most serious first) and tell me:\n"
             "Overall: how serious things are, in 1-2 sentences.\n"
             "Fix first: the top 3-5, each with why it matters and the first step.\n"
             "You can do yourself: (from items whose who_should_fix says 'yourself')\n"
             "Get help for: (items that need IT or a professional)\n"
             "End with one calm, encouraging sentence.\n\nProblems (JSON):\n" + json.dumps(items, indent=1)[:7000])
        return with_web(q), 2048
    if kind == "logs":
        rep = jload(hosts_file(acct), {}).get(str(b.get("id")))
        if not rep:
            raise RuntimeError("That server is no longer connected.")
        if not rep.get("logs"):
            raise RuntimeError("No logs were read on this server. Run the checker with the administrator option, "
                               "or add the user to the 'adm' group, then check again.")
        q = (f"Read the security log summary from my server '{rep.get('hostname')}' ({rep.get('os')}) below and explain it.\n"
             "Format:\nWhat the logs show:\nSigns of an attack: (Yes / No / Unclear, with the evidence)\n"
             "What to do: (numbered steps)\nWho should do it:\n"
             "If anything suggests someone actually got in (for example an unexpected successful sign-in), say clearly to contact a professional now.\n"
             "The IP addresses are where sign-in attempts came from.\n\nLog summary (JSON):\n" + json.dumps(rep["logs"], indent=1)[:9000])
        return with_web(q), 2048
    q = str(b.get("question", "")).strip()[:2000]
    if not q:
        raise RuntimeError("Type a question first.")
    return with_web(q), 2560


def summarize(payload):
    model = ai_model()
    items = payload.get("problems", [])[:25]
    if not items:
        return {"model": model, "text": "No problems were found on your connected servers. Keep automatic updates on and check again regularly."}
    prompt = (
        "You are a friendly security helper for the owner of a small organization who is NOT a computer expert.\n"
        "Below is the list of problems an automated checker found on their own servers (JSON). Use ONLY this list.\n"
        "Do not invent problems, numbers, CVEs or software versions. Plain everyday language, under 230 words.\n"
        "Use exactly this format:\n"
        "Overall: <1-2 sentences on how serious things are overall>\n"
        "Fix first:\n1. <problem in plain words> — <why it matters, simply>\n2. <...>\n3. <...>\n"
        "You can do yourself: <short comma list, from items whose who_should_fix says 'yourself', or 'none'>\n"
        "Get help for: <short comma list, from items whose who_should_fix mentions IT or a professional, or 'none'>\n"
        "Finish with one short, calm, encouraging sentence.\n\n"
        "Problems (JSON, most serious first):\n" + json.dumps(items, indent=1))
    return {"model": model, "text": generate(model, prompt, 420)}


def review_logs(acct, host_id):
    rep = jload(hosts_file(acct), {}).get(str(host_id))
    if not rep:
        raise RuntimeError("That server is no longer connected.")
    digest = rep.get("logs")
    if not digest:
        raise RuntimeError("No logs were read on this server. Run the checker with the administrator option, "
                           "or add the user to the 'adm' group, then check again.")
    model = ai_model()
    prompt = (
        "You are a security analyst helping the owner of a small organization who is NOT a computer expert.\n"
        f"Below is a summary of the security logs from their server '{rep.get('hostname')}' ({rep.get('os')}), produced by a log reader.\n"
        "Use ONLY this data. Do not invent events, numbers or addresses. If something is unclear, say so.\n"
        "IP addresses listed are where sign-in attempts came from. Plain everyday language, under 230 words.\n"
        "Use exactly this format:\n"
        "What the logs show: <2-3 simple sentences>\n"
        "Signs of an attack: <Yes / No / Unclear> — <the evidence, simply>\n"
        "What to do:\n1. <step>\n2. <step>\n3. <step>\n"
        "Who should do it: <'You can do this yourself' or 'Best with your IT person' or 'Call a security professional'>\n"
        "If there are signs that someone actually got in (for example an unexpected successful sign-in), say clearly to contact a professional now.\n\n"
        "Log summary (JSON):\n" + json.dumps(digest, indent=1)[:9000])
    return {"model": model, "text": generate(model, prompt, 450), "hostname": rep.get("hostname")}


def explain(ev):
    model = ai_model()
    prompt = (
        "You are a friendly security helper for someone who is NOT a computer expert, at a small organization.\n"
        "Use ONLY the evidence given. Do not invent facts, CVEs, versions or numbers. Do not change the risk score.\n"
        "Write under 170 words in simple, everyday language. Avoid jargon; if a technical word is unavoidable, explain it in a few words.\n"
        "Use exactly this format:\n"
        "What's wrong: <1-2 simple sentences>\n"
        "Why it matters to you: <1-2 sentences naming the affected services>\n"
        "What to do:\n1. <very simple step>\n2. <step>\n3. <step>\n"
        "Who should do it: <copy the 'how_hard' value>\n"
        "If 'call_professional' is true, add a final line clearly telling them to get a security professional and to limit who can use the affected system in the meantime.\n\n"
        "Evidence (JSON):\n" + json.dumps(ev, indent=1))
    return {"model": model, "text": generate(model, prompt, 320)}


def scan_self(acct):
    """Run the same read-only checks as the agent on this laptop and file them under the account."""
    sys.path.insert(0, HERE)
    import agent  # noqa: E402  (agent.py sits next to this file)
    as_root = hasattr(os, "geteuid") and os.geteuid() == 0
    rep = agent.check(as_root)
    rep["services"] = [s for s in rep["services"] if s.get("port") != PORT]
    rep["findings"] = [f for f in rep["findings"] if f.get("asset") != f"svc:{PORT}"]
    rep["hostname"] = f"{rep['hostname']} (this laptop)"
    rep["agent_id"] = "self-" + rep["agent_id"]
    save_report(acct, rep)
    return {"ok": True, "findings": len(rep["findings"]), "services": len(rep["services"])}


# ---------- HTTP ----------
LOCAL_ONLY = ("For safety, 'Scan this laptop' only works on the laptop running InfraSentinel. "
              "To check another machine, use 'Connect a server'.")
STATIC = {"/app.js": ("app.js", "application/javascript; charset=utf-8"),
          "/theme.css": ("theme.css", "text/css; charset=utf-8"),
          "/agent.py": ("agent.py", "text/x-python; charset=utf-8")}


class H(BaseHTTPRequestHandler):
    server_version = "InfraSentinel/0.2"

    def _send(self, code, body, ctype="application/json", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _file(self, name, ctype):
        with open(os.path.join(HERE, name), "rb") as f:
            return self._send(200, f.read(), ctype)

    def _body(self, limit=64_000):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > limit:
            raise ValueError("Request too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def _stream_ai(self, acct, body):
        try:
            model = ai_model()
            sources, web_state = [], "off"
            if body.get("web"):
                q = web_query(acct, body)
                if q:
                    sources = web_research(q)
                    web_state = "ok" if sources else "failed"
            messages, max_tokens = build_messages(acct, body, sources)
        except Exception as e:
            return self._send(503, {"error": str(e)})
        payload = {"model": model, "messages": messages, "stream": True, "think": False,
                   "options": {"temperature": 0.2, "num_predict": max_tokens, "num_ctx": NUM_CTX}}
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Model", model)
        self.send_header("X-Web", web_state)
        self.send_header("X-Sources", urllib.parse.quote(json.dumps([{"n": s["n"], "title": s["title"], "url": s["url"]} for s in sources])))
        self.send_header("Connection", "close")
        self.end_headers()

        def open_chat(p):
            req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(p).encode(), headers={"Content-Type": "application/json"})
            return urllib.request.urlopen(req, timeout=300)
        wrote, thought, in_think, buf = False, False, False, ""
        try:
            try:
                r = open_chat(payload)
            except urllib.error.HTTPError as e:
                if e.code == 400:                       # older Ollama or a model that rejects the 'think' option
                    payload.pop("think", None)
                    r = open_chat(payload)
                else:
                    raise
            with r:
                for line in r:
                    if not line.strip():
                        continue
                    j = json.loads(line)
                    msg = j.get("message") or {}
                    if msg.get("thinking"):
                        thought = True                  # hidden reasoning: not shown, but noted
                    piece = msg.get("content", "")
                    if piece:
                        buf += piece                    # drop <think>…</think> blocks some models put in the answer
                        out = ""
                        while True:
                            if in_think:
                                k = buf.find("</think>")
                                if k < 0:
                                    buf = buf[-7:]       # may hold the start of "</think>"
                                    break
                                buf, in_think = buf[k + 8:], False
                            else:
                                k = buf.find("<think>")
                                if k >= 0:
                                    out += buf[:k]; buf, in_think, thought = buf[k + 7:], True, True
                                    continue
                                hold = next((i for i in range(min(6, len(buf)), 0, -1) if "<think>".startswith(buf[-i:])), 0)
                                out += buf[:len(buf) - hold]
                                buf = buf[len(buf) - hold:]
                                break
                        if out:
                            if not wrote:
                                out = out.lstrip()
                            if out:
                                self.wfile.write(out.encode("utf-8")); self.wfile.flush(); wrote = True
                    if j.get("done"):
                        if not in_think and buf:
                            self.wfile.write(buf.encode("utf-8")); wrote = True
                        if j.get("done_reason") == "length":
                            if not wrote and thought:
                                self.wfile.write(("This model spent its whole answer budget thinking silently and never wrote an answer. "
                                                  "Pick a non-thinking model in the AI model list (for example Foundation-Sec 8B or Llama 3.1 8B), "
                                                  "or ask a shorter question.").encode())
                            else:
                                self.wfile.write("\n\n[The answer reached its length limit. Ask \"continue\" to get the rest.]".encode())
                        break
        except (BrokenPipeError, ConnectionResetError):
            return  # the person pressed Stop
        except Exception as e:
            try:
                self.wfile.write(f"\n\n[The AI stopped early: {e}. Try again.]".encode())
            except Exception:
                pass
        self.close_connection = True

    def _session(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        tok = c["is_session"].value if "is_session" in c else None
        s = SESSIONS.get(tok)
        if not s or s[1] < time.time():
            SESSIONS.pop(tok, None)
            return None, None
        email = s[0]
        u = jload(USERS_FILE, {}).get(email)
        return (email, u["acct"]) if u else (None, None)

    def _login_cookie(self, email):
        tok = secrets.token_urlsafe(24)
        SESSIONS[tok] = (email, time.time() + SESSION_TTL)
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        return {"Set-Cookie": f"is_session={tok}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL}{secure}"}

    def _end_session(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        if "is_session" in c:
            SESSIONS.pop(c["is_session"].value, None)

    def _remote(self):
        """True when the request came through the public tunnel or a proxy, not from this laptop directly."""
        return bool(self.headers.get("Cf-Connecting-Ip") or self.headers.get("X-Forwarded-For")) or \
            self.client_address[0] not in ("127.0.0.1", "::1")

    def _ai_allowed(self, acct):
        if not PUBLIC_URL or not self._remote():
            return True
        now = time.time()
        hits = [t for t in AI_USE.get(acct, []) if now - t < AI_LIMIT[1]]
        if len(hits) >= AI_LIMIT[0]:
            AI_USE[acct] = hits
            return False
        AI_USE[acct] = hits + [now]
        return True

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in STATIC:
            return self._file(*STATIC[path])
        email, acct = self._session()
        if path == "/api/config":
            org = jload(ACCOUNTS_FILE, {}).get(acct, {}).get("name") if acct else None
            return self._send(200, {"public": bool(PUBLIC_URL), "show_demo": not PUBLIC_URL,
                                    "signed_in": {"email": email, "org": org} if email else None})
        if path == "/login":
            return self._file("login.html", "text/html; charset=utf-8")   # always show it, so you can switch accounts
        if not email:
            if path in ("/", "/index.html"):
                return self._send(302, b"", "text/plain", {"Location": "/login"})
            return self._send(401, {"error": "Please sign in."})
        accts = jload(ACCOUNTS_FILE, {})
        a = accts.get(acct, {})
        if path in ("/", "/index.html"):
            return self._file("index.html", "text/html; charset=utf-8")
        if path == "/api/me":
            return self._send(200, {"email": email, "org": a.get("name"), "type": a.get("type"),
                                    "plan": a.get("plan", "free"), "billing": a.get("billing", "monthly")})
        if path == "/api/orgs":
            orgs = load_orgs()
            return self._send(200, {"organizations": orgs, "remediation": jload(state_file(acct), {})})
        if path == "/api/hosts":
            sector, summary = hosts_sector(acct, a.get("name", "Your organization"))
            return self._send(200, {"sector": sector, "hosts": summary, "now": int(time.time()), "email": email})
        if path == "/api/agent/info":
            urls = ([PUBLIC_URL] if PUBLIC_URL else []) + ([f"http://{lan_ip()}:{PORT}"] if LAN else [])
            urls.append(f"http://127.0.0.1:{PORT}")
            return self._send(200, {"token": a.get("token"), "urls": urls, "lan": LAN, "public": bool(PUBLIC_URL)})
        if path == "/api/scan" and self._remote():
            return self._send(403, {"error": LOCAL_ONLY})
        if path == "/api/scan":
            return self._send(200, scan())
        if path == "/api/ai-status":
            try:
                return self._send(200, {"ok": True, "model": pick_model()})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)})
        if path == "/api/ai/models":
            try:
                names = installed_models()
                return self._send(200, {"ok": True, "installed": names, "current": pick_model(), "recommended": RECOMMENDED})
            except Exception:
                return self._send(200, {"ok": False, "installed": [], "current": None, "recommended": RECOMMENDED, "error": AI_OFF})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            if path == "/api/agent/report":
                acct = acct_by_token(self.headers.get("X-Enroll-Token", ""))
                if not acct:
                    return self._send(403, {"error": "Unknown or reset enrollment token. Copy the command again from your dashboard."})
                rep = self._body(MAX_REPORT)
                hid = save_report(acct, rep)
                return self._send(200, {"ok": True, "host_id": hid})
            if path == "/api/agent/poll":
                acct = acct_by_token(self.headers.get("X-Enroll-Token", ""))
                if not acct:
                    return self._send(403, {"error": "Unknown or reset enrollment token. Copy the command again from your dashboard."})
                return self._send(200, {"scan": agent_poll(acct, self._body().get("agent_id"))})
            if path == "/api/login":
                b = self._body()
                email = check_login(str(b.get("email", "")), str(b.get("password", "")))
                if not email:
                    time.sleep(0.5)
                    return self._send(401, {"error": "That email and password don't match. Check them and try again."})
                self._end_session()
                return self._send(200, {"ok": True}, headers=self._login_cookie(email))
            if path == "/api/signup":
                b = self._body()
                if not str(b.get("org", "")).strip():
                    return self._send(400, {"error": "Enter your organization's name."})
                email = create_account(str(b["org"]), str(b.get("type", "smb")), str(b.get("email", "")), str(b.get("password", "")))
                self._end_session()
                return self._send(200, {"ok": True}, headers=self._login_cookie(email))
            if path == "/api/logout":
                c = SimpleCookie(self.headers.get("Cookie", ""))
                if "is_session" in c:
                    SESSIONS.pop(c["is_session"].value, None)
                return self._send(200, {"ok": True}, headers={"Set-Cookie": "is_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"})

            email, acct = self._session()
            if not email:
                return self._send(401, {"error": "Please sign in."})
            if path == "/api/remediation":
                b = self._body()
                st = jload(state_file(acct), {})
                st[str(b["org"]) + "/" + str(b["id"])] = {"status": b.get("status"), "evidence": str(b.get("evidence", ""))[:300]}
                jsave(state_file(acct), st)
                return self._send(200, {"ok": True})
            if path == "/api/plan":
                b = self._body()
                plan, billing = str(b.get("plan", "")), str(b.get("billing", "monthly"))
                if plan not in ("free", "starter", "pro") or billing not in ("monthly", "yearly"):
                    return self._send(400, {"error": "Unknown plan."})
                accts = jload(ACCOUNTS_FILE, {})
                accts[acct]["plan"], accts[acct]["billing"] = plan, billing
                jsave(ACCOUNTS_FILE, accts)
                return self._send(200, {"ok": True, "plan": plan, "billing": billing})
            if path == "/api/hosts/scan-now":
                request_scan(acct, self._body().get("id"))
                return self._send(200, {"ok": True})
            if path == "/api/hosts/remove":
                b = self._body()
                hosts = jload(hosts_file(acct), {})
                hosts.pop(str(b.get("id")), None)
                jsave(hosts_file(acct), hosts)
                return self._send(200, {"ok": True})
            if path == "/api/agent/reset-token":
                accts = jload(ACCOUNTS_FILE, {})
                accts[acct]["token"] = secrets.token_urlsafe(18)
                jsave(ACCOUNTS_FILE, accts)
                return self._send(200, {"ok": True, "token": accts[acct]["token"]})
            if path == "/api/scan-self":
                if self._remote():
                    return self._send(403, {"error": LOCAL_ONLY})
                return self._send(200, scan_self(acct))
            if path in ("/api/ai/stream", "/api/explain", "/api/ai/summary", "/api/ai/logs") and not self._ai_allowed(acct):
                return self._send(429, {"error": "You've asked the AI a lot in the last few minutes. Please wait a little and try again."})
            if path == "/api/ai/model" and self._remote():
                return self._send(403, {"error": "The AI model can only be changed on the laptop running InfraSentinel."})
            if path == "/api/ai/stream":
                return self._stream_ai(acct, self._body(200_000))
            if path == "/api/explain":
                try:
                    return self._send(200, explain(self._body()))
                except Exception as e:
                    return self._send(503, {"error": str(e)})
            if path == "/api/ai/summary":
                try:
                    return self._send(200, summarize(self._body()))
                except Exception as e:
                    return self._send(503, {"error": str(e)})
            if path == "/api/ai/logs":
                try:
                    return self._send(200, review_logs(acct, self._body().get("id")))
                except Exception as e:
                    return self._send(503, {"error": str(e)})
            if path == "/api/ai/model":
                want = str(self._body().get("model", ""))
                try:
                    names = installed_models()
                except Exception:
                    return self._send(503, {"error": AI_OFF})
                if want not in names:
                    return self._send(400, {"error": f"That model isn't downloaded yet. Run: ollama pull {want}"})
                st = jload(SETTINGS_FILE, {})
                st["model"] = want
                jsave(SETTINGS_FILE, st)
                return self._send(200, {"ok": True, "current": want})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            return self._send(400, {"error": f"Bad request: {e}"})
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *a):
        sys.stderr.write("  " + (fmt % a) + "\n")


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    made = ensure_demo()
    url = f"http://127.0.0.1:{PORT}/login"
    print(f"InfraSentinel running at {url}  (Ctrl+C to stop)")
    if LAN:
        print(f"Other machines on your network can connect at http://{lan_ip()}:{PORT}")
    if PUBLIC_URL:
        users = jload(USERS_FILE, {})
        if "demo@example.com" in users:
            pw = secrets.token_urlsafe(8)
            users["demo@example.com"]["salt"], users["demo@example.com"]["hash"] = hash_pw(pw)
            jsave(USERS_FILE, users)
            print("\n  PUBLIC LINK:  " + PUBLIC_URL + "\n")
            print(f"  Demo account for this session:  demo@example.com  /  {pw}")
            print("  (The usual demo password is switched off while the app is public. Share this one only with people you trust.)")
            print("  Anyone with the link can create their own account; they only ever see their own servers.\n")
    else:
        users = jload(USERS_FILE, {})
        if "demo@example.com" in users and hash_pw("demo1234", users["demo@example.com"]["salt"])[1] != users["demo@example.com"]["hash"]:
            users["demo@example.com"]["salt"], users["demo@example.com"]["hash"] = hash_pw("demo1234")
            jsave(USERS_FILE, users)
        if made:
            print("Demo account created:  demo@example.com  /  demo1234")
    o = load_orgs()
    print(f"Demo data: {len(o)} sample organizations, {sum(len(v.get('findings', [])) for v in o.values())} synthetic findings")
    try:
        print("AI model:", pick_model() or "none downloaded yet - start with: bash start.sh")
    except Exception:
        print("AI: Ollama not reachable - start it with: ollama serve   (app still works without AI)")
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), H)
    except OSError:
        sys.exit(f"\nInfraSentinel is already running on port {PORT} (maybe an older copy in another terminal).\n"
                 f"Stop it there with Ctrl+C, or run:  fuser -k {PORT}/tcp   then start again.")
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    httpd.serve_forever()
