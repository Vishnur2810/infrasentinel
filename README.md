# InfraSentinel

[![Tests](https://github.com/Vishnur2810/infrasentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/Vishnur2810/infrasentinel/actions/workflows/ci.yml) ![Version](https://img.shields.io/badge/version-0.5-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

**Plain-language security checks for small businesses, schools, colleges and clinics.**

InfraSentinel finds the security problems inside an organization's own servers and laptops, explains each one in plain words, tells the owner what to fix first and who should fix it, and records proof when it's fixed. A security-tuned AI model runs privately on your own machine to answer questions.

> Your cloud provider protects the cloud. InfraSentinel helps with your part of it:
> passwords, updates, open services, admin rights, settings, backups and logs.

![Overview](docs/screenshots/overview.png)

---

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Connect a server or PC](#connect-a-server-or-pc)
- [Share it publicly](#share-it-publicly)
- [How it works](#how-it-works)
- [What the checker looks at](#what-the-checker-looks-at)
- [How risk is scored](#how-risk-is-scored)
- [The AI assistant](#the-ai-assistant)
- [Security and privacy](#security-and-privacy)
- [Project structure](#project-structure)
- [Configuration](#configuration)
- [API](#api)
- [Run it 24/7](#run-it-247)
- [Tests](#tests)
- [What we fixed in 0.5](#what-we-fixed-in-05)
- [Limitations and roadmap](#limitations-and-roadmap)
- [Screenshots](#screenshots)

---

## Features

- **Accounts per organization.** Each organization signs in and only ever sees its own machines.
- **Connect any server or PC with one command.** A small, read-only checker for Linux, Windows and macOS reports what it finds. The command checks the checker's SHA-256 fingerprint before running it. Windows PCs without Python get a ready-made program.
- **Verified fixes.** Each new scan is compared with the last one: problems that disappeared are listed as *Verified fixes* automatically, and new problems are flagged.
- **Sees the rest of the network.** Lists other devices on the same network that aren't being checked, and warns if the router accepts unencrypted Telnet/FTP logins.
- **Problems in plain language.** Every problem has simple fix steps and a clear label: *You can do this yourself*, *Best with your IT person*, or *Call a security professional*.
- **Explainable risk scores.** A fixed formula ranks problems by severity, exposure and how important the asset is to the organization. The same flaw can be critical on one server and minor on another.
- **Checked steps first.** For every problem, steps written and reviewed by people (`playbook.json`) appear above the AI's answer, and still show when the AI is offline.
- **Ask the AI.** A local, security-tuned model (Cisco Foundation-Sec 8B via Ollama) explains problems, reviews all of them, reads log summaries, and answers follow-up questions. Optional web search cites its sources. Commands appear in copyable code boxes, and commands that could delete data, switch off protection or lock you out are flagged in red or amber.
- **Scan now, remotely.** A machine can stay listening so the dashboard can trigger a fresh scan from anywhere, without opening any ports.
- **Security log reading.** Failed sign-ins and where they came from, root/administrator sign-ins, failed admin attempts, new accounts, system errors.
- **Fix list with proof.** A fix only counts as verified when evidence is recorded.
- **Impact map and simulation** (Advanced view). See which business services depend on an asset and what a failure would affect.
- **15 weakness categories** with the problems found in each, plus *Ask AI* and *What is this?* buttons.
- **Account & security.** 2-step sign-in (authenticator app), password change, a "who to call" contact shown on every serious problem, download-my-data and delete-my-account.
- **Sample subscription plans**, light/dark theme, iOS-style Liquid Glass design, phone-friendly layout.

## Quick start

Requirements: **Linux or macOS**, **Python 3.9+** (standard library only). Optional: [Ollama](https://ollama.com/download) for the AI assistant (an 8 GB GPU is comfortable; CPU works but is slower).

```bash
git clone https://github.com/Vishnur2810/infrasentinel.git
cd infrasentinel
bash start.sh
```

Open **http://127.0.0.1:8765** and sign in with the demo account **demo@example.com / demo1234**, or create your own account.

The first time, `start.sh` starts Ollama and downloads the AI model (about 5 GB). Then press **Scan this laptop** to check the machine running InfraSentinel.

| Command | What it does |
|---|---|
| `bash start.sh` | Dashboard for this computer only |
| `bash start.sh --lan` | Also reachable by machines on the same Wi-Fi / network |
| `bash start.sh --public` | A public `https://…trycloudflare.com` link anyone can open |

## Connect a server or PC

In the dashboard, open **Your servers → Connect a server**, pick **Linux or Mac** or **Windows**, choose the options, and copy the command. Run it on the machine you want to check.

Linux / macOS (shortened; the dashboard gives you the full command):

```bash
curl -fsSL https://YOUR-DASHBOARD/agent.py -o infrasentinel-agent.py \
  && python3 -c "…exit unless the SHA-256 matches FINGERPRINT…" \
  && python3 infrasentinel-agent.py --server https://YOUR-DASHBOARD --token YOUR-ACCESS-CODE --watch
```

Windows: one command that works in Command Prompt, PowerShell or Windows Terminal. If Python is installed, it downloads `agent.py`, checks its fingerprint with `Get-FileHash`, then runs it. If Python isn't installed, it downloads `infrasentinel-agent.exe` from this repository's latest GitHub release.

The dashboard fills in your address, access code and the checker's fingerprint (also at `/agent.py.sha256`). If the downloaded file doesn't match, it is not run.

Checker options:

| Option | Meaning |
|---|---|
| `--watch` | Stay running so the dashboard's **Scan now** works (checks in every 15 s, re-checks every 6 h) |
| `--install` | Keep it running after restarts (cron on Linux, Task Scheduler on Windows) |
| `--dry-run` | Print exactly what would be sent, and send nothing |
| `--no-logs` | Don't read or send any log information |
| `--no-network` | Don't look at other devices on the network or contact the router |
| `--every 2` | With `--watch`: hours between automatic full checks (default 6) |
| `--uninstall` | Remove the schedule and files |

Run with `sudo` (Linux) or an administrator terminal (Windows) to include admin-only checks.

## Share it publicly

```bash
bash start.sh --public
```

This downloads Cloudflare's free tunnel program once and prints a public HTTPS link. It stays open while the terminal runs; **Ctrl+C** closes it. The quick link changes each start.

**Permanent address:** create a named tunnel in the Cloudflare dashboard (Zero Trust → Networks → Tunnels, pointing to `http://127.0.0.1:8765`), then:

```bash
CF_TUNNEL_TOKEN=<token> IS_PUBLIC_URL=https://scan.yourdomain.com bash start.sh --public
```

While public:

- the demo password is replaced by a one-off password printed in the terminal
- **Scan this laptop** and changing the AI model only work on the host machine
- each account can make 20 AI requests per 10 minutes
- "Connect a server" commands use the public link, so machines anywhere can report in

## How it works

```
 Owner's browser  ⟷  InfraSentinel server  ⟷  Checker on each machine
  (dashboard)          (Python, this repo)      (agent.py, read-only)
                              │
                 ┌────────────┴────────────┐
           Local AI (Ollama)        Web search (optional)
           Foundation-Sec 8B        DuckDuckGo / Ollama web search
```

1. The owner signs in and copies a command from **Connect a server**.
2. The checker reads the machine's settings and logs and sends a report over HTTPS with the organization's access code.
3. The server scores each problem, attaches fix steps and "who should fix it", and shows it in the dashboard.
4. With `--watch`, the checker asks the server every 15 seconds whether someone pressed **Scan now**. All connections go outward, so no firewall changes are needed.

The server uses only the Python standard library. Data is stored in one SQLite database, `data/infrasentinel.db` (file mode 600). Set `IS_ENCRYPT=1` to encrypt it (needs `pip install cryptography`). Data from older versions (JSON files) is moved in automatically on first start, and the originals are kept in `data/legacy-json/`.

## What the checker looks at

All checks are read-only.

**Linux:** services open to the network · SSH password and root login · waiting security patches, with the names of the affected packages · automatic updates · OS end of support · firewall service · extra admin (UID 0) accounts · admin group size · password file permissions · empty passwords (sudo) · backup tools · security logs for the last 7 days (failed sign-ins and sources, root sign-ins, failed sudo, new accounts, system errors).

**Windows:** Windows Firewall per network profile · Microsoft Defender real-time protection and definition age · days since the last update · auto-update policy · Windows version support · Remote Desktop and Network Level Authentication · SMBv1 · administrators, built-in Administrator, Guest · UAC · password length and lockout · BitLocker (admin) · backup tools / File History · event logs (4625 failed sign-ins, 4624 remote sign-ins, 4720 new accounts, System errors).

**macOS:** services open to the network · firewall · FileVault disk encryption · waiting updates · automatic security responses · Gatekeeper · System Integrity Protection · macOS version support · administrator count · Time Machine backups.

**Every OS (unless `--no-network`):** other devices in the machine's neighbour/ARP table that aren't being checked · whether the router accepts Telnet (23) or FTP (21). That is one connection attempt to the router per port; no other device is contacted.

Every problem is filed under one of 15 categories: weak passwords, outdated software, missing patches, broken access control, SQL injection, cross-site scripting, misconfiguration, excessive permissions, insecure APIs, exposed remote access, missing backups, poor network segmentation, insecure encryption, vulnerable third-party software, unsupported devices.

## How risk is scored

```
Risk = 0.4 × Severity + 0.3 × Exposure + 0.3 × Criticality
```

- **Severity** (0–100): CVSS score × 10.
- **Exposure:** internet 90 · local network 70 · internal 45 · isolated 15 · unknown 50 (flagged, never assumed safe).
- **Criticality:** importance to the organization. An asset inherits the criticality of the most important service that depends on it.

Bands: **Critical 80–100**, **High 60–79**, **Medium 30–59**, **Low 0–29**. Anything Critical is always marked *Call a security professional*.

The AI never changes a score. The weights are a starting point to be calibrated with real pilots. Change them without touching code with `IS_WEIGHTS=0.5,0.3,0.2` (they must add up to 1). The dashboard shows the formula with the weights in use.

## The AI assistant

- Runs through **Ollama** on your own machine. The default model is **Foundation-Sec-8B-Instruct** (Cisco Foundation AI, built on Llama 3.1 8B), about 5 GB. Switch models in **Ask the AI → AI model**.
- Explains one problem, reviews all problems, reads a server's log summary, or answers your own questions, with follow-ups.
- Uses only your scan data for facts about your systems; general security knowledge for how-to steps.
- Hidden "thinking" is turned off so answers aren't cut short; answers stream in as they're written.
- **Safety:** reviewed *Checked steps* are shown above every explanation. The AI is told never to suggest destructive commands and to warn before lock-out risks. The dashboard flags dangerous commands (deleting files, turning off the firewall or antivirus, `curl | bash`) in red, and lock-out risks (SSH or firewall changes) in amber. Every answer is labelled as AI-written.
- **Queue:** at most `IS_AI_SLOTS` (default 2) answers are written at once; others wait up to 90 seconds, then get a "busy, try again" message instead of slowing everyone down.
- **Search the web** (on by default): searches for the problem plus your OS, reads the top pages, and cites them as [1], [2]. Only public pages are fetched; private network addresses are blocked. Set `OLLAMA_API_KEY` to use Ollama's web search, or `IS_SEARCH_URL` to use your own SearXNG instance, instead of DuckDuckGo. Results are cached for 6 hours.

## Security and privacy

- The checker only reads; `--dry-run` shows exactly what is sent; `--uninstall` removes it.
- The checker only reports on the machine it runs on. It never scans other machines.
- Passwords are hashed with PBKDF2-SHA256 (200,000 rounds). Optional 2-step sign-in with any authenticator app. Wrong passwords are rate-limited (5 per account / 20 per address per 15 min). Sessions are HttpOnly cookies that expire after 12 hours; changing the password signs out other devices.
- Each organization has its own data and access code. A leaked access code can only send reports; **Reset access code** disables old commands, and the dashboard reminds you after 90 days.
- Scan results and logs go only to the local AI. With web search on, only the search words leave the machine.
- Users can download all their data or delete their account (*Account & security*). See the [privacy notice](privacy.html) and [terms](terms.html), written with India's DPDP Act 2023 in mind (templates: have them reviewed before commercial use).
- Forgotten password or lost phone: the operator runs `python3 server.py --reset-password EMAIL`.
- Traffic is plain HTTP on your own network; use `--public` or a named tunnel / reverse proxy for HTTPS.
- Only connect machines you own or are authorized to check.
- Full details: [SECURITY.md](SECURITY.md).

## Project structure

```
infrasentinel/
├── server.py              Web server and API: accounts, sessions, reports, scoring data, AI, web search, public mode
├── agent.py               Read-only checker for Linux, Windows and macOS (Python standard library only)
├── index.html             Dashboard (problems, fixes, impact map, coverage, Ask the AI)
├── app.js                 App layer: navigation, servers, Scan now, AI chat, plans, theme
├── theme.css              Liquid Glass theme (light and dark)
├── login.html             Sign-in and create-account page
├── playbook.json          Reviewed fix steps for the 15 categories (shown before AI answers)
├── privacy.html, terms.html
├── start.sh               Starts Ollama, downloads the model, opens a public link with --public
├── Dockerfile, docker-compose.yml   Always-on deployment with the AI helper
├── deploy/                systemd service + installer (starts at boot, restarts on failure)
├── tests/                 End-to-end tests (server, agent, playbook safety)
├── .github/workflows/     Tests on Linux/Windows/macOS; builds the Windows .exe on each release tag
├── data/
│   └── organizations.json Sample organizations for demos (Advanced view)
└── docs/
    ├── pitch-prep.html    Team briefing and judge Q&A practice
    └── screenshots/
```

Created at runtime and **not** committed (see `.gitignore`): `data/infrasentinel.db`, `data/secret.key`, `data/legacy-json/`, `bin/cloudflared`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `IS_PORT` | `8765` | Port for the dashboard |
| `IS_MODEL` | Foundation-Sec 8B | Ollama model to download and prefer |
| `IS_CTX` | `12288` | AI context window (tokens) |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Where Ollama runs |
| `OLLAMA_API_KEY` | – | Use Ollama's web search for "Search the web" |
| `IS_BIND=0.0.0.0` | – | Same as `--lan` |
| `IS_DATA` | `./data` | Where the database lives |
| `IS_ENCRYPT=1` | off | Encrypt stored data (key in `data/secret.key`, or `IS_DATA_KEY`) |
| `IS_WEIGHTS` | `0.4,0.3,0.3` | Risk weights: severity, exposure, criticality |
| `IS_AI_SLOTS` | `2` | AI answers written at the same time |
| `IS_SEARCH_URL` | – | Your SearXNG address for web search |
| `IS_PUBLIC_URL` + `CF_TUNNEL_TOKEN` | – | Permanent public address with a named Cloudflare tunnel |
| `IS_AGENT_EXE_URL` | latest GitHub release | Where Windows PCs without Python get the checker |

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/signup`, `/api/login`, `/api/logout` | Accounts |
| GET | `/api/me`, `/api/config` | Current user, public-mode settings |
| GET | `/api/hosts` | Connected machines and their problems |
| POST | `/api/hosts/scan-now`, `/api/hosts/remove` | Request a scan, remove a machine |
| GET | `/api/agent/info` | Access code and command address |
| POST | `/api/agent/report`, `/api/agent/poll` | Used by the checker (access-code header) |
| POST | `/api/agent/reset-token` | Disable old commands |
| POST | `/api/scan-self` | Scan the host machine (local only) |
| POST | `/api/ai/stream` | Streamed AI answers (explain, summary, logs, chat) |
| GET/POST | `/api/ai/models`, `/api/ai/model` | List / choose the AI model |
| POST | `/api/remediation`, `/api/plan` | Save fix status, choose a sample plan |
| POST | `/api/2fa/setup`, `/api/2fa/enable`, `/api/2fa/disable` | 2-step sign-in |
| POST | `/api/password`, `/api/contact`, `/api/account/delete` | Change password, "who to call" contact, delete account |
| GET | `/api/account/export` | Download all your data (JSON) |
| GET | `/agent.py.sha256`, `/api/health` | Checker fingerprint, health check |

## Run it 24/7

A laptop that sleeps can't serve the dashboard. For always-on use, run it on an always-on PC, a server or a small cloud VM:

```bash
# Option A: Docker (dashboard + AI helper, data encrypted at rest)
docker compose up -d
docker compose exec ollama ollama pull hf.co/mradermacher/Foundation-Sec-8B-Instruct-GGUF:Q4_K_M

# Option B: systemd service (starts at boot, restarts if it stops)
sudo bash deploy/install-service.sh
```

Add a named Cloudflare tunnel (above) or a reverse proxy such as Caddy for a permanent HTTPS address.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests start a real server with an empty database and cover sign-up and sign-in, 2-step codes, the sign-in rate limit, separate accounts, access-code reset, fix verification between scans, data export and delete, migration from older data, the checker's fingerprint, network-device parsing and the safety of the reviewed fix steps. GitHub Actions runs them on Linux, Windows and macOS for every push.

## What we fixed in 0.5

Weak points raised when we reviewed the prototype, and what changed:

| Weak point | What we did |
|---|---|
| Windows needed Python | Ready-made `infrasentinel-agent.exe` built by GitHub Actions on every release; the Windows command uses it automatically when Python is missing |
| JSON files, risk of clashing saves | One SQLite database with a single write lock; old data migrated automatically |
| Everything stops when the laptop sleeps | Docker Compose and a systemd service for an always-on machine |
| Public link changes every restart | Named Cloudflare tunnel support for a permanent address |
| Only checked settings, not known vulnerabilities | Names the packages with published security fixes waiting (apt/dnf security advisories) |
| Other devices on the network unseen | Lists unchecked devices; checks the router for Telnet/FTP |
| Admin-only checks silently missing | Each machine shows "Basic checks" and what was skipped |
| macOS barely supported | 10 macOS checks |
| Only checked every 6 hours | `--every` sets any interval; **Scan now** works any time |
| AI could be wrong or unsafe | Reviewed checked steps shown first; risky commands flagged; safety rules in the prompt; answers labelled AI-written |
| AI slow with many users | Answer queue (`IS_AI_SLOTS`) and 6-hour web-search cache |
| Web search could break | SearXNG option and caching, plus two DuckDuckGo endpoints |
| No proof a fix worked | Automatic *Verified fixes* on every re-scan; "1 fixed, 1 new since last check" per machine |
| No 2-step sign-in or password reset | Authenticator-app codes, password change, operator reset, sign-in rate limit |
| Access code never expires | Age shown, reminder after 90 days, one-click reset |
| Data stored unencrypted | `IS_ENCRYPT=1` encryption at rest; database readable only by its owner |
| Checker not verified | SHA-256 fingerprint checked by every install command |
| No privacy policy, terms or data rights | Privacy notice and terms (DPDP Act 2023), data export and account deletion |
| "Call a professional" led nowhere | Saved "who to call" contact on every serious problem; CERT-In reporting note in the terms |
| Risk weights fixed in code | `IS_WEIGHTS` setting, shown in the formula |
| No license, no tests | MIT license; end-to-end tests on three operating systems |

## Limitations and roadmap

**Still open:** no independent security audit yet · the checker isn't code-signed (fingerprints and GitHub-built releases instead) · no website code testing (SQL injection / XSS) · full CVE matching for every installed package (today: packages with waiting security fixes) · plans are samples with no payments · score weights need calibrating with real pilots · no customers yet · password reset needs the operator (no email yet) · privacy notice and terms are templates to be reviewed by a lawyer.

**Next:** pilots with 3–5 schools and clinics · payments · email/WhatsApp alerts · team roles · import findings from Greenbone, Wazuh and OWASP ZAP · code-signed installers · a partner list of local IT professionals.

## Screenshots

| | |
|---|---|
| ![Sign in](docs/screenshots/login.png) | ![Problems and fix steps](docs/screenshots/problems.png) |
| ![Ask the AI](docs/screenshots/ask-ai.png) | ![Coverage](docs/screenshots/coverage.png) |
| ![Impact map](docs/screenshots/impact-map.png) | ![Plans](docs/screenshots/plans.png) |

<p align="center"><img src="docs/screenshots/phone.png" width="300" alt="Phone view"></p>

## Credits

- [Ollama](https://ollama.com) for running local models
- [Foundation-Sec-8B-Instruct](https://huggingface.co/fdtn-ai/Foundation-Sec-8B-Instruct) by Cisco Foundation AI (check its license before commercial use)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) for public links

Released under the [MIT License](LICENSE).
