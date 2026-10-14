"""End-to-end tests: start a real server on a free port with an empty data folder and use the API like the app does.
Run:  python3 -m unittest discover -s tests -v"""
import hashlib, http.cookiejar, json, os, socket, subprocess, sys, tempfile, time, unittest, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Client:
    def __init__(self, base):
        self.base = base
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json", **(headers or {})},
                                   method="POST" if data is not None else "GET")
        try:
            with self.op.open(r, timeout=20) as res:
                raw = res.read()
                return res.status, (json.loads(raw) if res.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw


def report(agent_id, finding_ids):
    return {"agent_id": agent_id, "hostname": "test-box", "os": "Ubuntu 24.04", "checked_at": int(time.time()), "services": [],
            "findings": [{"id": f, "title": f"Problem {f}", "severity": 6, "exposure": "internal", "asset": "host",
                          "details": {"category": "misconfig"}} for f in finding_ids], "skipped": []}


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        # old-style JSON files from v0.4, to prove they get moved into the database
        salt = "00" * 16
        h = hashlib.pbkdf2_hmac("sha256", b"old password 1", bytes.fromhex(salt), 200_000).hex()
        with open(os.path.join(cls.tmp, "users.json"), "w") as f:
            json.dump({"old@example.com": {"acct": "old-org", "salt": salt, "hash": h, "created": 1}}, f)
        with open(os.path.join(cls.tmp, "accounts.json"), "w") as f:
            json.dump({"old-org": {"name": "Old Org", "type": "smb", "token": "oldtoken", "created": 1}}, f)
        cls.port = free_port()
        env = dict(os.environ, IS_DATA=cls.tmp, IS_PORT=str(cls.port), OLLAMA_HOST="http://127.0.0.1:9")
        cls.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py"), "--no-browser"], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + "/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)

    def signup(self, email):
        c = Client(self.base)
        code, j = c.req("/api/signup", {"org": "Test School " + email, "type": "school", "email": email, "password": "correct horse 1"})
        self.assertEqual(code, 200, j)
        return c

    def test_health_and_static(self):
        c = Client(self.base)
        self.assertEqual(c.req("/api/health")[1]["ok"], True)
        code, pb = c.req("/playbook.json")
        self.assertEqual(code, 200)
        self.assertEqual(len([k for k in pb if not k.startswith("_")]), 15)
        for page in ("/privacy", "/terms", "/login"):
            self.assertEqual(c.req(page)[0], 200, page)
        code, cfg = c.req("/api/config")
        self.assertAlmostEqual(sum(cfg["weights"]), 1.0)

    def test_agent_fingerprint(self):
        code, raw = Client(self.base).req("/agent.py.sha256")
        with open(os.path.join(ROOT, "agent.py"), "rb") as f:
            self.assertEqual(raw.decode().split()[0], hashlib.sha256(f.read()).hexdigest())

    def test_requires_login(self):
        c = Client(self.base)
        self.assertEqual(c.req("/api/hosts")[0], 401)
        self.assertEqual(c.req("/api/remediation", {"org": "x", "id": "y"})[0], 401)

    def test_fix_verification(self):
        c = self.signup("verify@example.com")
        tok = c.req("/api/agent/info")[1]["token"]
        h = {"X-Enroll-Token": tok}
        self.assertEqual(c.req("/api/agent/report", report("box1", ["a", "b", "c"]), h)[0], 200)
        self.assertEqual(c.req("/api/agent/report", report("box1", ["b", "c", "d"]), h)[0], 200)
        host = c.req("/api/hosts")[1]["hosts"][0]
        self.assertEqual(host["diff"]["fixed"], ["Problem a"])
        self.assertEqual(host["diff"]["new"], ["Problem d"])
        self.assertEqual([r["id"] for r in host["resolved"]], ["a"])
        self.assertEqual(len(host["history"]), 2)
        # a "fixed" problem that comes back is no longer counted as fixed
        c.req("/api/agent/report", report("box1", ["a", "b"]), h)
        host = c.req("/api/hosts")[1]["hosts"][0]
        self.assertNotIn("a", [r["id"] for r in host["resolved"]])
        # an agent can't fake its own history
        bad = report("box1", ["b"]); bad["resolved"] = [{"id": "zzz", "title": "fake"}]
        c.req("/api/agent/report", bad, h)
        self.assertNotIn("zzz", [r["id"] for r in c.req("/api/hosts")[1]["hosts"][0]["resolved"]])

    def test_token_reset(self):
        c = self.signup("token@example.com")
        old = c.req("/api/agent/info")[1]["token"]
        new = c.req("/api/agent/reset-token", {})[1]["token"]
        self.assertNotEqual(old, new)
        self.assertEqual(c.req("/api/agent/report", report("x", []), {"X-Enroll-Token": old})[0], 403)
        self.assertEqual(c.req("/api/agent/report", report("x", []), {"X-Enroll-Token": new})[0], 200)

    def test_accounts_are_separate(self):
        a, b = self.signup("a@example.com"), self.signup("b@example.com")
        ta = a.req("/api/agent/info")[1]["token"]
        a.req("/api/agent/report", report("only-a", ["p"]), {"X-Enroll-Token": ta})
        self.assertEqual(len(a.req("/api/hosts")[1]["hosts"]), 1)
        self.assertEqual(b.req("/api/hosts")[1]["hosts"], [])

    def test_two_step_signin(self):
        import server
        c = self.signup("tfa@example.com")
        secret = c.req("/api/2fa/setup", {})[1]["secret"]
        self.assertEqual(c.req("/api/2fa/enable", {"code": "000000"})[0], 400)
        self.assertEqual(c.req("/api/2fa/enable", {"code": server.totp(secret)})[0], 200)
        self.assertTrue(c.req("/api/me")[1]["two_factor"])
        d = Client(self.base)
        code, j = d.req("/api/login", {"email": "tfa@example.com", "password": "correct horse 1"})
        self.assertEqual(code, 401); self.assertTrue(j.get("need_code"))
        code, j = d.req("/api/login", {"email": "tfa@example.com", "password": "correct horse 1", "code": server.totp(secret)})
        self.assertEqual(code, 200, j)

    def test_login_throttle(self):
        self.signup("throttle@example.com")
        c = Client(self.base)
        codes = [c.req("/api/login", {"email": "throttle@example.com", "password": "wrong"})[0] for _ in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)
        self.assertEqual(c.req("/api/login", {"email": "throttle@example.com", "password": "correct horse 1"})[0], 429)

    def test_password_change_export_delete(self):
        c = self.signup("life@example.com")
        self.assertEqual(c.req("/api/password", {"password": "nope", "new": "another long pass"})[0], 403)
        self.assertEqual(c.req("/api/password", {"password": "correct horse 1", "new": "another long pass"})[0], 200)
        self.assertEqual(c.req("/api/contact", {"name": "Ravi IT", "phone": "+91 90000 00000"})[1]["contact"]["name"], "Ravi IT")
        code, data = c.req("/api/account/export")
        self.assertEqual(code, 200)
        self.assertNotIn("token", data["organization"])
        self.assertEqual(c.req("/api/account/delete", {"password": "another long pass"})[0], 200)
        self.assertEqual(Client(self.base).req("/api/login", {"email": "life@example.com", "password": "another long pass"})[0], 401)

    def test_legacy_json_migrated(self):
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "infrasentinel.db")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "users.json")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "legacy-json", "users.json")))
        c = Client(self.base)
        self.assertEqual(c.req("/api/login", {"email": "old@example.com", "password": "old password 1"})[0], 200)
        self.assertEqual(c.req("/api/me")[1]["org"], "Old Org")


def load_playbook():
    with open(os.path.join(ROOT, "playbook.json")) as f:
        return json.load(f)


class AgentTest(unittest.TestCase):
    def test_network_parsing(self):
        import agent
        neigh = ("192.168.1.1 dev wlan0 lladdr aa:bb:cc:dd:ee:01 REACHABLE\n192.168.1.20 dev wlan0 lladdr aa:bb:cc:dd:ee:02 STALE\n"
                 "192.168.1.21 dev wlan0  FAILED\n192.168.1.30 dev wlan0 lladdr aa:bb:cc:dd:ee:03 STALE\n"
                 "192.168.1.31 dev wlan0 lladdr aa:bb:cc:dd:ee:04 STALE\n")
        orig_run, orig_po = agent.run, agent.port_open
        try:
            agent.run = lambda cmd, t=30: (0, neigh) if cmd[:2] == ["ip", "neigh"] else (
                (0, "default via 192.168.1.1 dev wlan0") if cmd[:2] == ["ip", "route"] else (None, ""))
            agent.port_open = lambda h, p, timeout=1.5: p == 23
            rep = agent.add_network_findings({"ip": "192.168.1.5", "findings": [], "skipped": []})
            ids = [f["id"] for f in rep["findings"]]
            self.assertIn("router-telnet", ids)
            self.assertIn("unchecked-devices", ids)
            self.assertEqual(len(rep["network"]["devices"]), 3)
            agent.run = lambda cmd, t=30: (0, "  192.168.0.1   a4-2b-b0-11-22-33   dynamic\n  192.168.0.255  ff-ff-ff-ff-ff-ff  static\n") \
                if cmd[0] == "arp" else (None, "")
            self.assertEqual(agent.neighbours(), [{"ip": "192.168.0.1", "mac": "a4:2b:b0:11:22:33"}])
        finally:
            agent.run, agent.port_open = orig_run, orig_po

    @unittest.skipIf(sys.platform == "darwin" and os.environ.get("CI"), "softwareupdate -l is slow on CI runners")
    def test_report_shape(self):
        import agent
        rep = agent.full_check(False, logs=False, network=False)
        for k in ("agent_id", "hostname", "os", "services", "findings", "skipped"):
            self.assertIn(k, rep)
        for f in rep["findings"]:
            self.assertIn(f["details"]["category"], load_playbook())


class PlaybookSafetyTest(unittest.TestCase):
    def test_no_dangerous_steps(self):
        import re
        bad = re.compile(r"rm -rf|mkfs|ufw disable|chmod 777|format c:|Remove-Item", re.I)
        pb = load_playbook()
        for k, v in pb.items():
            if k.startswith("_"):
                continue
            for step in v["steps"] + [v["verify"]]:
                self.assertIsNone(bad.search(step), f"{k}: {step}")


if __name__ == "__main__":
    unittest.main()
