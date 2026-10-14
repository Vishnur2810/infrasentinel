/* InfraSentinel application layer: account bar, connect-a-server flow, live "My servers" results,
   and the "Ask the AI" assistant (streamed answers, follow-up questions).
   Runs after the console script and uses its globals (SECTORS, cur, sel, sim, tasks, initTasks, renderAll, $, esc,
   data, score, band, fixInfo, FIXLVL, VNAME, node, EXPO_LBL, missing). */
(function () {
  try { const t = localStorage.getItem("is_theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) {}
  const css = `
  [hidden]{display:none!important}
  .userbar{display:flex;flex-wrap:wrap;gap:8px 14px;justify-content:flex-end;align-items:center;font-size:13px;color:var(--muted)}
  .userbar b{color:var(--ink);font-weight:600}
  .linkbtn{border:0;background:none;color:var(--accent);font:600 13px var(--f-body);cursor:pointer;padding:0}
  .steps3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:4px 0 14px}
  .step{border:1px solid var(--line);border-radius:8px;padding:12px;display:grid;gap:6px;align-content:start;min-width:0}
  .step .num{width:24px;height:24px;border-radius:50%;background:var(--accent-soft);color:var(--accent);font:600 12px var(--f-mono);display:grid;place-items:center}
  .step b{font-size:14px}
  .step p{margin:0;font-size:13px;color:var(--muted)}
  pre.cmd{margin:0;background:var(--node);border:1px solid var(--line);border-radius:6px;padding:10px 12px;font:12.5px/1.5 var(--f-mono);white-space:pre-wrap;word-break:break-all;color:var(--ink)}
  .cmdrow{display:grid;gap:8px}
  .opts{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px}
  .opts label{display:flex;gap:6px;align-items:center;cursor:pointer}
  .warnnote{font-size:13px;border-left:3px solid var(--med);background:var(--med-soft);padding:8px 11px;border-radius:0 6px 6px 0}
  .hostok{color:var(--low);font-weight:600}
  .online{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;color:var(--low);margin-top:3px}
  .online::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--low)}
  .btn.mini{padding:6px 13px!important;font-size:12.5px!important;margin-bottom:4px}
  .live{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
  .live::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--low);animation:pulse 2s infinite}
  @keyframes pulse{50%{opacity:.3}}
  .logline{font-size:12px;color:var(--muted);margin-top:2px}
  .logline b{color:var(--ink)}
  .aimeta{font:500 11px var(--f-mono);color:var(--muted);margin-top:8px}
  .aiwait{display:flex;gap:10px;align-items:center;font-size:14px;color:var(--muted)}
  .spin{width:16px;height:16px;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite;flex:none}
  @keyframes spin{to{transform:rotate(360deg)}}
  #assistant{display:grid;gap:14px}
  .asst-tools{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center}
  .asst-tools select{max-width:100%}
  .chat{display:grid;gap:14px;min-height:220px;max-height:min(72vh,820px);overflow-y:auto;padding:14px;border:1px solid var(--line);border-radius:10px;background:var(--bg);scroll-behavior:smooth}
  .chat-empty{color:var(--muted);font-size:14px;align-self:center;justify-self:center;text-align:center;max-width:52ch}
  .msg{max-width:100%;min-width:0}
  .msg.me{justify-self:end;background:var(--accent);color:var(--panel);padding:9px 13px;border-radius:12px 12px 2px 12px;font-size:14px;max-width:min(80%,640px);white-space:pre-wrap}
  .msg.ai{background:var(--panel);border:1px solid var(--line);border-radius:2px 12px 12px 12px;padding:14px 18px}
  .ans{white-space:pre-wrap;font-size:15px;line-height:1.7;max-width:90ch;overflow-wrap:anywhere}
  .ans b{font-weight:600}
  .ans code{font:13px var(--f-mono);background:var(--node);padding:1px 5px;border-radius:4px}
  .suggest{display:flex;flex-wrap:wrap;gap:8px}
  .suggest button{border:1px solid var(--line);background:var(--panel);color:var(--ink);font:13px var(--f-body);padding:6px 11px;border-radius:999px;cursor:pointer}
  .suggest button:hover{border-color:var(--accent);color:var(--accent)}
  .askrow{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:end}
  .askrow textarea{font:15px/1.5 var(--f-body);color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:11px 12px;resize:vertical;min-height:52px;width:100%}
  .askbtns{display:flex;gap:8px}
  .btn.stop{background:var(--crit);border-color:var(--crit)}
  .webtog{display:inline-flex;align-items:center;gap:8px;font:600 13px var(--f-body);cursor:pointer;user-select:none}
  .webtog input{position:absolute;opacity:0;width:1px;height:1px}
  .webtog .tog{width:42px;height:26px;border-radius:999px;background:var(--line);position:relative;transition:background .25s;flex:none}
  .webtog .tog::after{content:"";position:absolute;top:2px;left:2px;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 2px 6px rgba(0,0,0,.25);transition:transform .25s}
  .webtog input:checked + .tog{background:#34C759}
  .webtog input:checked + .tog::after{transform:translateX(16px)}
  .webtog input:focus-visible + .tog{outline:2px solid var(--accent);outline-offset:2px}
  .srcs{display:grid;gap:6px;margin-top:12px;padding-top:10px;border-top:1px solid var(--line);font-size:13px}
  .srcs b{font-size:12px;color:var(--muted)}
  .srcs a{color:var(--accent);text-decoration:none;display:flex;gap:8px;align-items:baseline;min-width:0}
  .srcs a span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .srcs a small{color:var(--muted);flex:none}
  .srcs a:hover span{text-decoration:underline}
  a.cite{display:inline-block;font:700 11px var(--f-body);color:var(--accent);background:var(--accent-soft);border-radius:6px;padding:0 5px;margin:0 1px;text-decoration:none;vertical-align:1px}
  .difline{font-size:12px;margin-top:3px;color:var(--muted)}
  .difline .ok{color:var(--low);font-weight:600}.difline .nw{color:var(--crit);font-weight:600}
  .verified{margin-top:14px;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
  .verified h3{margin:0 0 6px;font-size:14px}
  .verified ul{margin:0;padding:0;list-style:none;display:grid;gap:5px;font-size:13px}
  .verified li::before{content:"✓";color:var(--low);font-weight:700;margin-right:8px}
  .verified small{color:var(--muted)}
  .fpr{font:11.5px var(--f-mono);color:var(--muted);word-break:break-all}
  .codebox.risky{outline:2px solid var(--crit);outline-offset:2px}
  .riskcmd{font-size:13px;border-left:3px solid var(--crit);background:var(--crit-soft,rgba(255,59,48,.1));padding:7px 10px;border-radius:0 6px 6px 0;margin:6px 0}
  .lockcmd{font-size:13px;border-left:3px solid var(--med);background:var(--med-soft);padding:7px 10px;border-radius:0 6px 6px 0;margin:6px 0}
  .checked{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:12px;background:var(--bg)}
  .checked h4{margin:0 0 6px;font-size:13px;display:flex;gap:8px;align-items:center}
  .checked h4 span{font:600 11px var(--f-body);color:var(--low);background:rgba(52,199,89,.14);padding:2px 8px;border-radius:999px}
  .checked ol{margin:0 0 6px;padding-left:20px;font-size:14px;line-height:1.6}
  .checked .muted{font-size:13px}
  .aiwarn{font:600 11px var(--f-body);color:var(--med);margin-left:8px}
  .sec-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
  .sec-card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:grid;gap:8px;align-content:start;min-width:0}
  .sec-card h3{margin:0;font-size:15px}
  .sec-card p{margin:0;font-size:13px;color:var(--muted)}
  .sec-card input{font:14px var(--f-body);color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 10px;width:100%;box-sizing:border-box}
  .sec-card a.btn{text-decoration:none}
  .sec-card .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  .pill{display:inline-block;font:600 12px var(--f-body);padding:2px 9px;border-radius:999px;background:var(--line)}
  .pill.on{background:rgba(52,199,89,.16);color:var(--low)}
  #qr{background:#fff;padding:8px;border-radius:8px;width:max-content}
  .secret{font:13px var(--f-mono);letter-spacing:.06em;word-break:break-all}
  .secmsg{font-size:13px}
  .procontact{display:block;margin-top:6px;font-weight:600}
  @media (max-width:800px){.sec-grid{grid-template-columns:1fr}}
  @media (prefers-reduced-motion:reduce){.live::before,.spin{animation:none}.chat{scroll-behavior:auto}}
  @media (max-width:800px){.steps3{grid-template-columns:1fr}.askrow{grid-template-columns:1fr}}`;
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  const wrap = document.querySelector(".wrap"), header = wrap.querySelector("header");
  const bar = document.createElement("div"); bar.className = "userbar"; bar.id = "userbar";
  wrap.insertBefore(bar, header);

  /* ---------- "Your servers" panel ---------- */
  const sec = document.createElement("section"); sec.className = "panel"; sec.id = "servers";
  sec.innerHTML = `
    <div class="panel-head">
      <div><h2>Your servers</h2><div class="muted" style="font-size:13px">Connect the servers your organization runs. The checker only reads settings and logs. It doesn't change anything.</div></div>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span class="live" id="liveflag" hidden>Watching for new results</span><button class="btn" id="connBtn" type="button">Connect a server</button></div>
    </div>
    <div id="connSteps" hidden>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px"><span class="eyebrow">The machine runs</span>
        <div class="seg" id="osPick" role="group" aria-label="Operating system"><button type="button" data-os="linux" aria-pressed="true">Linux or Mac</button><button type="button" data-os="windows" aria-pressed="false">Windows</button></div></div>
      <div class="steps3">
        <div class="step"><span class="num">1</span><b id="step1t">Open the server</b><p id="step1p">Open a terminal on the server you want to check. It needs Python 3, which most Linux servers already have.</p></div>
        <div class="step"><span class="num">2</span><b>Paste one command</b><p>Copy the command below, paste it into the terminal and press Enter.</p></div>
        <div class="step"><span class="num">3</span><b>See the results here</b><p id="step3p">Problems and simple fixes appear on this page within a few seconds.</p></div>
      </div>
      <div class="cmdrow">
        <div class="opts">
          <label for="optWatch"><input type="checkbox" id="optWatch" checked> Let me scan it from this dashboard ("Scan now")</label>
          <label for="optInstall"><input type="checkbox" id="optInstall"> Keep it running after restarts</label>
          <label for="optSudo"><input type="checkbox" id="optSudo"> <span id="optSudoTxt">Include administrator-only checks (asks for the server's password)</span></label>
        </div>
        <pre class="cmd" id="cmd">Loading…</pre>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <button class="btn" id="copyBtn" type="button">Copy command</button>
          <span id="copyMsg" class="muted" style="font-size:13px"></span>
          <span style="flex:1"></span>
          <button class="linkbtn" id="resetTok" type="button">Reset access code</button>
        </div>
        <div class="fpr" id="fpr"></div>
        <div id="lanNote"></div>
        <div class="src">The command downloads the checker from this dashboard and runs it once. Add <code>--dry-run</code> to see exactly what it would send, or <code>--no-logs</code> to skip log reading. To remove a scheduled checker, run the checker again with <code>--uninstall</code>.</div>
      </div>
    </div>
    <div class="tbl" style="margin-top:12px"><table>
      <thead><tr><th>Server</th><th>System</th><th>Last checked</th><th>Problems</th><th></th></tr></thead>
      <tbody id="hostRows"><tr><td colspan="5" class="muted">No servers connected yet. Press "Scan this laptop" or "Connect a server" to add your first one.</td></tr></tbody>
    </table></div>`;
  const hint = document.getElementById("simplehint");
  hint.parentNode.insertBefore(sec, hint.nextSibling);

  /* ---------- "Ask the AI" panel ---------- */
  const asst = document.createElement("section"); asst.className = "panel"; asst.id = "assistant";
  asst.innerHTML = `
    <div class="panel-head" style="margin:0">
      <div><h2>Ask the AI</h2><div class="muted" style="font-size:13px">Ask anything about your servers' problems and logs, in your own words. The AI runs on this laptop and answers from your scan results.</div></div>
      <div class="asst-tools">
        <label for="aiModel" class="eyebrow">AI model</label><select id="aiModel"><option>Checking…</option></select>
        <label class="webtog" for="webOn" title="Look up fixes online and cite the sources"><input type="checkbox" id="webOn"><span class="tog"></span>Search the web</label>
        <button class="btn" id="aiSumBtn" type="button">Review all problems</button>
      </div>
    </div>
    <div id="modelMsg" class="muted" style="font-size:12px" hidden></div>
    <div id="modelHint"></div>
    <div class="chat" id="chat" aria-live="polite"><div class="chat-empty" id="chatEmpty">Press <b>Review all problems</b>, tap a suggested question, or type your own below. You can ask follow-up questions like "explain step 2 in more detail".</div></div>
    <div class="suggest" id="suggest">
      <button type="button">Is my laptop safe right now?</button>
      <button type="button">What should I fix first today?</button>
      <button type="button">Explain the failed sign-ins in my logs</button>
      <button type="button">How do I turn on automatic updates?</button>

    </div>
    <form class="askrow" id="askForm">
      <label for="askInput" class="eyebrow" style="grid-column:1/-1">Your question</label>
      <textarea id="askInput" rows="2" placeholder="e.g. Someone tried to log in 60 times. Should I be worried?"></textarea>
      <div class="askbtns"><button class="btn" id="askSend" type="submit">Ask</button>
        <button class="btn stop" id="askStop" type="button" hidden>Stop</button>
        <button class="btn ghost" id="askClear" type="button" title="Start a new conversation">Clear</button></div>
    </form>`;
  sec.parentNode.insertBefore(asst, sec.nextSibling);

  const scanning = {};
  function alertNote(msg) {
    let n = $("hostNote"); if (!n) { n = document.createElement("div"); n.id = "hostNote"; sec.appendChild(n); }
    n.innerHTML = `<div class="warnnote" style="margin-top:10px">${esc(msg)}</div>`; setTimeout(() => { n.innerHTML = ""; }, 8000);
  }
  let info = null, lastSig = "", firstHosts = true, removing = null, resetArm = false, aiReady = false;

  function ago(ts) {
    if (!ts) return "—";
    const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + " min ago";
    if (s < 86400) return Math.floor(s / 3600) + " h ago";
    return Math.floor(s / 86400) + " days ago";
  }
  const shortModel = m => {
    const n = String(m || "");
    if (/foundation-sec/i.test(n)) return "Foundation-Sec 8B (security)";
    return n.replace(/^hf\.co\/[^/]+\//, "").replace(/-GGUF/i, "").replace(/:latest$/, "");
  };
  // Friendlier AI status pill in the toolbar
  window.aiStatus = async function () {
    const el = $("aistat"); if (!el) return;
    try {
      const j = await (await fetch("/api/ai-status")).json();
      el.innerHTML = j.ok && j.model ? `<span class="is-dot ok"></span>AI ready · ${esc(shortModel(j.model))}` : `<span class="is-dot"></span>AI offline · app still works`;
    } catch (e) { el.innerHTML = `<span class="is-dot"></span>AI needs the local server`; }
  };
  window.aiStatus();

  /* ---------- connect a server ---------- */
  let osPick = "linux";
  function buildCmd() {
    if (!info) return;
    const url = info.urls[0];
    const inst = ($("optWatch").checked ? " --watch" : "") + ($("optInstall").checked ? " --install" : "");
    const win = osPick === "windows";
    $("step1t").textContent = win ? "Open PowerShell" : "Open the server";
    $("step1p").innerHTML = win
      ? (($("optSudo").checked ? "Right-click Start and choose <b>Terminal (Admin)</b>. " : "Press Start, type <b>cmd</b> or <b>PowerShell</b> and open it. ") +
         "The command works in either. If Python isn't installed, it downloads the ready-made Windows program instead.")
      : "Open a terminal on the server you want to check. It needs Python 3, which most Linux servers and Macs already have.";
    $("step3p").textContent = $("optWatch").checked
      ? ($("optInstall").checked ? "Results appear here in a few seconds. It keeps running in the background, so you can press “Scan now” any time."
                                 : "Results appear here in a few seconds. Leave that window open, and you can press “Scan now” here any time.")
      : "Problems and simple fixes appear on this page within a few seconds.";
    $("optSudoTxt").textContent = win ? "Include administrator-only checks (sign-in logs, disk encryption, SMBv1)" : "Include administrator-only checks (asks for the server's password)";
    const args = `--server ${url} --token ${info.token}${inst}`, h = info.sha256;
    // Every command checks the downloaded checker against its published SHA-256 fingerprint before running it.
    $("cmd").textContent = win
      ? `powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Set-Location ([IO.Path]::GetTempPath()); ` +
        `if ((Get-Command py -EA 0) -or (Get-Command python -EA 0)) { irm ${url}/agent.py -OutFile infrasentinel-agent.py; ` +
        `if ((Get-FileHash infrasentinel-agent.py -Algorithm SHA256).Hash -ne '${h}') { Write-Host 'Safety check failed: the downloaded checker does not match its fingerprint. It was NOT run.' } ` +
        `elseif (Get-Command py -EA 0) { py infrasentinel-agent.py ${args} } else { python infrasentinel-agent.py ${args} } } ` +
        `else { irm '${info.exe_url}' -OutFile infrasentinel-agent.exe; .\\infrasentinel-agent.exe ${args} }"`
      : `curl -fsSL ${url}/agent.py -o infrasentinel-agent.py && python3 -c "import hashlib,sys;sys.exit(hashlib.sha256(open('infrasentinel-agent.py','rb').read()).hexdigest()!='${h}' and 'Safety check failed: the checker does not match its fingerprint. Not run.')" && ${$("optSudo").checked ? "sudo " : ""}python3 infrasentinel-agent.py ${args}`;
    $("fpr").textContent = `Checker fingerprint (SHA-256): ${h}. The command refuses to run a file that doesn't match.` + (win ? " Without Python, it uses the ready-made Windows program from the project's GitHub releases." : "");
    $("lanNote").innerHTML = info.public ? `<div class="src">This command uses your public link, so it works on servers anywhere on the internet.</div>` : info.lan ? "" :
      `<div class="warnnote">This address works for a checker on <b>this laptop</b> only. To connect a machine elsewhere, restart with <code>bash start.sh --public</code> (anywhere on the internet) or <code>bash start.sh --lan</code> (same network), then copy the command again.</div>`;
  }
  async function loadInfo() {
    const r = await fetch("/api/agent/info");
    if (r.status === 401) return (location.replace("/login"));
    info = await r.json(); buildCmd();
  }
  function showSteps(show) {
    $("connSteps").hidden = !show;
    $("connBtn").textContent = show ? "Hide steps" : "Connect a server";
    if (show && !info) loadInfo();
  }
  $("connBtn").onclick = () => {
    const opening = $("connSteps").hidden;
    showSteps(opening);
    if (opening) $("connSteps").scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  $("optInstall").onchange = buildCmd; $("optSudo").onchange = buildCmd; $("optWatch").onchange = buildCmd;
  $("osPick").querySelectorAll("button").forEach(b => b.onclick = () => {
    osPick = b.dataset.os; $("osPick").querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); buildCmd();
  });
  $("copyBtn").onclick = async () => {
    const txt = $("cmd").textContent;
    try { await navigator.clipboard.writeText(txt); $("copyMsg").textContent = "Copied. Paste it into the server's terminal."; }
    catch (e) { const r = document.createRange(); r.selectNodeContents($("cmd")); const s = getSelection(); s.removeAllRanges(); s.addRange(r); $("copyMsg").textContent = "Selected. Press Ctrl+C to copy."; }
  };
  $("resetTok").onclick = async () => {
    if (!resetArm) { resetArm = true; $("resetTok").textContent = "Old commands will stop working. Click again to reset"; setTimeout(() => { resetArm = false; $("resetTok").textContent = "Reset access code"; }, 5000); return; }
    resetArm = false; $("resetTok").textContent = "Reset access code";
    const r = await fetch("/api/agent/reset-token", { method: "POST" }); const j = await r.json();
    if (j.token) { info.token = j.token; buildCmd(); $("copyMsg").textContent = "New access code created. Copy the command again."; }
  };

  /* ---------- scan this laptop ---------- */
  const scanBtn = $("scanBtn");
  if (scanBtn) {
    scanBtn.disabled = false; scanBtn.title = "";
    scanBtn.onclick = async () => {
      scanBtn.disabled = true; scanBtn.textContent = "Scanning this laptop…";
      try {
        const r = await fetch("/api/scan-self", { method: "POST" });
        if (r.status === 401) return (location.replace("/login"));
        if (r.status === 403) {
          const j = await r.json().catch(() => ({}));
          scanBtn.textContent = "Only on the laptop itself"; scanBtn.title = j.error || ""; scanBtn.disabled = false;
          showSteps(true); $("connSteps").scrollIntoView({ behavior: "smooth", block: "center" });
          return;
        }
        if (!r.ok) throw new Error("scan failed");
        lastSig = ""; await poll();
        if (SECTORS.mine && cur !== "mine") { cur = "mine"; sel = null; sim = null; initTasks(); renderAll(); }
        scanBtn.textContent = "Scan this laptop again";
        if (aiReady) aiSummary(); else asst.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (e) { scanBtn.textContent = "Scan failed, try again"; }
      scanBtn.disabled = false;
    };
  }

  /* ---------- server list ---------- */
  function diffLine(h) {
    const d = h.diff; if (!d) return "";
    const fx = (d.fixed || []).length, nw = (d.new || []).length;
    if (!fx && !nw) return `<div class="difline">No change since the last check</div>`;
    return `<div class="difline">Since last check: ${fx ? `<span class="ok">${fx} fixed ✓</span>` : ""}${fx && nw ? " · " : ""}${nw ? `<span class="nw">${nw} new</span>` : ""}</div>`;
  }
  let verifiedCount = 0;
  function renderVerified(hosts) {
    const all = [];
    hosts.forEach(h => (h.resolved || []).forEach(r => all.push({ ...r, host: h.hostname })));
    all.sort((a, b) => b.fixed_at - a.fixed_at);
    verifiedCount = all.length;
    let box = $("verifiedBox");
    if (!box) { box = document.createElement("div"); box.id = "verifiedBox"; sec.appendChild(box); }
    box.innerHTML = all.length ? `<div class="verified"><h3>Verified fixes</h3><div class="muted" style="font-size:12px;margin-bottom:8px">Confirmed automatically: the problem was found before and is gone in the newest check.</div>
      <ul>${all.slice(0, 8).map(r => `<li>${esc(r.title)} <small>· ${esc(r.host)} · ${new Date(r.fixed_at * 1000).toLocaleDateString()}</small></li>`).join("")}</ul></div>` : "";
  }
  function renderHosts(hosts) {
    renderVerified(hosts);
    if (!hosts.length) {
      $("hostRows").innerHTML = `<tr><td colspan="5" class="muted">No servers connected yet. Press "Scan this laptop" or "Connect a server" to add your first one.</td></tr>`;
      return;
    }
    const logLine = l => !l ? `<div class="logline">Logs: not readable without administrator rights</div>` :
      `<div class="logline">Logs: ${l.failed_logins == null ? "sign-in attempts need administrator rights" : `<b>${l.failed_logins}</b> failed sign-ins`} · <b>${l.sudo_failures || 0}</b> failed admin attempts${l.root_logins ? ` · <b>${l.root_logins}</b> root sign-ins` : ""}${l.system_errors_24h != null ? ` · <b>${l.system_errors_24h}</b> system errors (24 h)` : ""}</div>`;
    $("hostRows").innerHTML = hosts.map(h => `<tr>
      <td><b>${esc(h.hostname)}</b><div class="src">${esc(h.ip || "")}</div>${logLine(h.logs)}</td>
      <td>${esc(h.os || "")}${h.as_root ? "" : `<div class="src">Basic checks · run with administrator option for more</div>`}</td>
      <td>${ago(h.received_at)}${h.online ? `<div class="online">Online</div>` : ""}</td>
      <td>${h.findings ? `<b>${h.findings}</b> to review` : `<span class="hostok">None found</span>`}${diffLine(h)}${h.network && h.network.devices ? `<div class="difline">${h.network.devices} other device${h.network.devices === 1 ? "" : "s"} seen on its network</div>` : ""}</td>
      <td style="white-space:nowrap">${h.online ? `<button class="btn mini" data-scan="${esc(h.id)}" type="button"${h.scan_requested || scanning[h.id] ? " disabled" : ""}>${h.scan_requested || scanning[h.id] ? "Scanning…" : "Scan now"}</button><br>` : ""}
        ${h.logs ? `<button class="linkbtn" data-logs="${esc(h.id)}" data-name="${esc(h.hostname)}" type="button">Read logs with AI</button><br>` : ""}
        <button class="linkbtn" data-rm="${esc(h.id)}" type="button">${removing === h.id ? "Click again to remove" : "Remove"}</button></td></tr>`).join("");
    hosts.forEach(h => { if (scanning[h.id] && h.received_at > scanning[h.id]) delete scanning[h.id]; });
    $("hostRows").querySelectorAll("button[data-scan]").forEach(b => b.onclick = async () => {
      const id = b.dataset.scan; b.disabled = true; b.textContent = "Scanning…";
      try {
        const r = await fetch("/api/hosts/scan-now", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) });
        const j = await r.json(); if (!r.ok) throw new Error(j.error);
        scanning[id] = Math.floor(Date.now() / 1000);
      } catch (e) { b.disabled = false; b.textContent = "Scan now"; b.title = e.message; alertNote(e.message); }
    });
    $("hostRows").querySelectorAll("button[data-logs]").forEach(b => b.onclick = () =>
      ask({ kind: "logs", id: b.dataset.logs }, `Read the security logs of ${b.dataset.name} and tell me what's going on.`));
    $("hostRows").querySelectorAll("button[data-rm]").forEach(b => b.onclick = async () => {
      const id = b.dataset.rm;
      if (removing !== id) { removing = id; renderHosts(hosts); setTimeout(() => { if (removing === id) { removing = null; renderHosts(hosts); } }, 5000); return; }
      removing = null;
      await fetch("/api/hosts/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) });
      lastSig = ""; poll();
    });
  }
  function putMineFirst(sector) {
    const rest = {}; for (const k of Object.keys(SECTORS)) if (k !== "mine") { rest[k] = SECTORS[k]; delete SECTORS[k]; }
    delete SECTORS.mine; SECTORS.mine = sector; Object.assign(SECTORS, rest);
  }
  async function poll() {
    let j;
    try { const r = await fetch("/api/hosts", { cache: "no-store" }); if (r.status === 401) return (location.replace("/login")); j = await r.json(); }
    catch (e) { return; }
    if (shownAs && j.email && j.email !== shownAs) return location.reload();   // signed in as someone else in another tab
    renderHosts(j.hosts || []);
    $("liveflag").hidden = !(j.hosts || []).length;
    const sig = JSON.stringify(j.sector);
    if (sig === lastSig) return;
    lastSig = sig;
    if (!j.sector) {
      if (SECTORS.mine) { delete SECTORS.mine; if (cur === "mine") { cur = Object.keys(SECTORS)[0]; sel = null; sim = null; initTasks(); } renderAll(); }
      return;
    }
    const had = !!SECTORS.mine;
    putMineFirst(j.sector);
    if (firstHosts || !had) {
      firstHosts = false; cur = "mine"; sel = null; sim = null; initTasks();
      if (typeof applySaved === "function") applySaved();
      showSteps(false);
    } else if (cur === "mine") {
      const old = tasks; initTasks(); for (const k in old) if (tasks[k]) tasks[k] = old[k];
      if (!data().findings.some(f => f[0] === sel)) sel = null;
      if (sim && !data().nodes.some(n => n[0] === sim)) sim = null;
    }
    renderAll();
  }

  /* ---------- the assistant ---------- */
  const history = [];           // [{role, content}] sent back for follow-up questions
  let streaming = null;

  // Clean Markdown for AI answers: headings, lists, labels, links, citations, and code boxes with a Copy button.
  function inline(text, srcs) {
    const codes = [];
    let h = String(text).replace(/`([^`\n]+)`/g, (m, c) => { codes.push(c); return "\u0000" + (codes.length - 1) + "\u0000"; });
    h = esc(h);
    h = h.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, t, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`);
    if (srcs && srcs.length) h = h.replace(/\[(\d{1,2})\]/g, (m, n) => {
      const s = srcs.find(x => String(x.n) === n);
      return s ? `<a class="cite" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" title="${esc(s.title)}">${n}</a>` : m;
    });
    h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>").replace(/__([^_\n]+)__/g, "<b>$1</b>");
    h = h.replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,;:!?]|$)/g, "$1<i>$2</i>");
    return h.replace(/\u0000(\d+)\u0000/g, (m, i) => `<code>${esc(codes[+i])}</code>`);
  }
  const RISKY = /\brm\s+-[a-z]*[rf]|\bmkfs|\bdd\s+if=|>\s*\/dev\/sd|\bformat\s+[a-z]:|chmod\s+(-R\s+)?0?777|\bufw\s+disable|systemctl\s+(stop|disable|mask)\s+(ufw|firewalld|nftables|unattended)|setenforce\s+0|Set-MpPreference[^\n]*Disable|netsh\s+advfirewall\s+set\s+\w+\s+state\s+off|Set-NetFirewallProfile[^\n]*-Enabled\s+False|Remove-Item[^\n]*-Recurse|\bdel\s+\/[sq]|\brd\s+\/s|(curl|wget)[^|\n]*\|\s*(sudo\s+)?(ba|z)?sh|\b(iwr|irm|Invoke-WebRequest)[^|\n]*\|\s*iex|\buserdel\b|\bdeluser\b|DROP\s+(TABLE|DATABASE)/i;
  const LOCKOUT = /PasswordAuthentication\s+no|PermitRootLogin\s+no|\bufw\s+(enable|default\s+deny)|iptables\s+-P\s+INPUT\s+DROP|Set-NetFirewallRule|fDenyTSConnections|passwd\s+-l|usermod\s+-L/i;
  function md(t, srcs) {
    t = String(t).replace(/<think>[\s\S]*?(<\/think>|$)/g, "").replace(/\r/g, "");
    const lines = t.split("\n"), out = [];
    let para = [], list = null;
    const flushPara = () => { if (para.length) { out.push(`<p>${para.map(l => inline(l, srcs)).join("<br>")}</p>`); para = []; } };
    const flushList = () => { if (list) { out.push(`<${list.type}${list.start > 1 ? ` start="${list.start}"` : ""}>${list.items.map(i => `<li>${inline(i, srcs)}</li>`).join("")}</${list.type}>`); list = null; } };
    const flush = () => { flushPara(); flushList(); };
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const fence = line.match(/^\s*```\s*([\w+#.-]*)\s*$/);
      if (fence) {                                   // fenced code block (may still be streaming in)
        flush();
        const lang = fence[1] || "", body = [];
        i++;
        while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) body.push(lines[i++]);
        const code = body.join("\n").replace(/^\n+|\n+$/g, "");
        const danger = RISKY.test(code), lock = !danger && LOCKOUT.test(code);
        if (danger) out.push(`<div class="riskcmd"><b>Careful:</b> this command can delete data or switch off protection. Don't run it unless your IT person has checked it.</div>`);
        if (lock) out.push(`<div class="lockcmd"><b>Could lock you out:</b> keep a second window or another way into this machine open until you've confirmed you can still sign in.</div>`);
        out.push(`<div class="codebox${danger ? " risky" : ""}"><div class="codehead"><span>${esc(lang || "command")}</span><button class="copybtn" type="button">Copy</button></div><pre><code>${esc(code)}</code></pre></div>`);
        continue;
      }
      if (!line.trim()) { flush(); continue; }
      let m;
      if ((m = line.match(/^\s*#{1,6}\s+(.+?)\s*#*\s*$/))) { flush(); out.push(`<h4>${inline(m[1].replace(/:$/, ""), srcs)}</h4>`); continue; }
      if ((m = line.match(/^\s*(?:\*\*)?([A-Z][A-Za-z'’ /&()-]{2,40}):(?:\*\*)?\s*(.*)$/)) && !/^https?$/i.test(m[1]) && !/^\s*\d/.test(line)) {
        flush(); out.push(`<h4>${esc(m[1])}</h4>`);         // "What's wrong:" style labels
        if (m[2].trim()) para.push(m[2].replace(/^\*\*\s*/, ""));
        continue;
      }
      if ((m = line.match(/^\s*(\d+)[.)]\s+(.*)$/))) {
        flushPara();
        if (!list || list.type !== "ol") { flushList(); list = { type: "ol", start: +m[1], items: [] }; }
        list.items.push(m[2]); continue;
      }
      if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) {
        flushPara();
        if (!list || list.type !== "ul") { flushList(); list = { type: "ul", start: 1, items: [] }; }
        list.items.push(m[1]); continue;
      }
      if (list && /^\s{2,}\S/.test(line)) { list.items[list.items.length - 1] += " " + line.trim(); continue; }
      flushList(); para.push(line.trim());
    }
    flush();
    return out.join("");
  }
  // Copy buttons for code boxes and whole answers (one listener for the whole chat)
  async function copyText(txt, btn, label) {
    try { await navigator.clipboard.writeText(txt); btn.textContent = "Copied"; }
    catch (e) { btn.textContent = "Select and press Ctrl+C"; }
    setTimeout(() => { btn.textContent = label; }, 1600);
  }
  document.addEventListener("click", e => {
    const b = e.target.closest(".copybtn");
    if (b) return copyText(b.closest(".codebox").querySelector("code").textContent, b, "Copy");
    const a = e.target.closest(".copyans");
    if (a) return copyText(a.closest(".msg").querySelector(".ans").innerText, a, "Copy answer");
  });
  function setBusy(b) {
    $("askSend").hidden = b; $("askStop").hidden = !b; $("aiSumBtn").disabled = b;
    $("suggest").querySelectorAll("button").forEach(x => x.disabled = b);
  }
  function nearBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 120; }

  async function ask(body, label) {
    if (streaming) streaming.abort();
    const chat = $("chat"); $("chatEmpty")?.remove();
    const me = document.createElement("div"); me.className = "msg me"; me.textContent = label; chat.appendChild(me);
    const ai = document.createElement("div"); ai.className = "msg ai";
    const useWeb = $("webOn").checked && (body.kind === "chat" || body.kind === "explain");
    ai.innerHTML = `<div class="aiwait"><span class="spin"></span>${useWeb ? "Searching the web for solutions, then writing the answer…" : "Thinking… the first answer can take up to a minute while the model loads."}</div>`;
    chat.appendChild(ai);
    asst.scrollIntoView({ behavior: "smooth", block: "start" });
    chat.scrollTop = chat.scrollHeight;
    const ctrl = new AbortController(); streaming = ctrl; setBusy(true);
    let text = "", model = "";
    const pb = body.checked && PLAYBOOK && PLAYBOOK[body.checked];
    const checkedCard = pb ? `<div class="checked"><h4>Checked steps <span>Reviewed by people</span></h4><ol>${pb.steps.map(x => `<li>${esc(x)}</li>`).join("")}</ol><div class="muted"><b>How to check it worked:</b> ${esc(pb.verify)}</div></div>` : "";
    try {
      const r = await fetch("/api/ai/stream", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, web: useWeb, history: history.slice(-8) }), signal: ctrl.signal });
      if (r.status === 401) return (location.replace("/login"));
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || "The AI helper is unavailable."); }
      model = r.headers.get("X-Model") || "";
      let srcs = []; try { srcs = JSON.parse(decodeURIComponent(r.headers.get("X-Sources") || "%5B%5D")); } catch (e) {}
      const webState = r.headers.get("X-Web") || "off";
      if (useWeb) ai.querySelector(".aiwait") && (ai.querySelector(".aiwait").lastChild.textContent = srcs.length ? `Read ${srcs.length} web page${srcs.length > 1 ? "s" : ""}. Writing the answer…` : "Couldn't reach web search. Answering from the scan and the model's own knowledge…");
      const ans = document.createElement("div"); ans.className = "ans";

      const rd = r.body.getReader(), dec = new TextDecoder();
      let started = false;
      while (true) {
        const { done, value } = await rd.read();
        if (done) break;
        text += dec.decode(value, { stream: true });
        if (!started && text.trim()) { ai.innerHTML = checkedCard + (checkedCard ? `<div class="eyebrow" style="margin-bottom:6px">AI explanation for your machine</div>` : ""); ai.appendChild(ans); started = true; }
        const stick = nearBottom(chat);
        ans.innerHTML = md(text, srcs);
        if (stick) chat.scrollTop = chat.scrollHeight;
      }
      if (!started) ai.innerHTML = `<div class="warnnote">The AI returned an empty answer. Try again, or pick another model above.</div>`;
      if (srcs.length) ai.insertAdjacentHTML("beforeend", `<div class="srcs"><b>Sources the AI read</b>${srcs.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"><small>[${s.n}]</small><span>${esc(s.title)}</span><small>${esc(new URL(s.url).hostname.replace(/^www\./, ""))}</small></a>`).join("")}</div>`);
      ai.insertAdjacentHTML("beforeend", `<div class="aifoot"><button class="copyans" type="button">Copy answer</button><span class="aimeta">AI-written by ${esc(shortModel(model))} · check each step before running it${webState === "ok" ? " · used web sources" : webState === "failed" ? " · web search unavailable" : ""}</span></div>`);
    } catch (e) {
      if (e.name === "AbortError") ai.insertAdjacentHTML("beforeend", `<div class="aimeta">Stopped.</div>`);
      else ai.innerHTML = checkedCard + `<div class="warnnote">${esc(e.message)}${checkedCard ? " The checked steps above still apply." : ""}</div>`;
    }
    if (text.trim()) history.push({ role: "user", content: label }, { role: "assistant", content: text });
    if (streaming === ctrl) { streaming = null; setBusy(false); }
  }

  $("askForm").addEventListener("submit", e => {
    e.preventDefault();
    const q = $("askInput").value.trim(); if (!q) return $("askInput").focus();
    $("askInput").value = ""; ask({ kind: "chat", question: q }, q);
  });
  $("askInput").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("askForm").requestSubmit(); } });
  $("askStop").onclick = () => { if (streaming) streaming.abort(); };
  $("askClear").onclick = () => {
    if (streaming) streaming.abort();
    history.length = 0;
    $("chat").innerHTML = `<div class="chat-empty" id="chatEmpty">New conversation. Ask a question or press <b>Review all problems</b>.</div>`;
  };
  $("suggest").querySelectorAll("button").forEach(b => b.onclick = () => ask({ kind: "chat", question: b.textContent }, b.textContent));

  function problemsForAI() {
    if (!SECTORS.mine) return [];
    const prev = cur; cur = "mine";
    try {
      return data().findings.map(f => {
        const s = score(f), fi = fixInfo(f, s);
        return { problem: f[1], server: node(f[2]).name, risk_band: band(s.R), risk_score: s.R,
                 category: VNAME[fi.id], who_should_fix: FIXLVL[fi.level][0] };
      }).sort((a, b) => b.risk_score - a.risk_score);
    } finally { cur = prev; }
  }
  function aiSummary() {
    if (!SECTORS.mine) {
      $("chatEmpty")?.remove();
      $("chat").insertAdjacentHTML("beforeend", `<div class="msg ai"><div class="warnnote">Scan this laptop or connect a server first, then ask the AI to review.</div></div>`);
      return;
    }
    const problems = problemsForAI();
    ask({ kind: "summary", problems }, `Review all ${problems.length} problem${problems.length === 1 ? "" : "s"} on my servers. What should I fix first?`);
  }
  $("aiSumBtn").onclick = aiSummary;
  try { $("webOn").checked = localStorage.getItem("is_web") !== "0"; } catch (e) { $("webOn").checked = true; }
  $("webOn").onchange = () => { try { localStorage.setItem("is_web", $("webOn").checked ? "1" : "0"); } catch (e) {} };

  // The "Explain in simple words (AI)" button on each problem now answers in this big panel.
  window.askAI = function (f, s, n, svcs) {
    const fi = fixInfo(f, s);
    const evidence = { problem: f[1], asset: n.name, source: f[5], severity_0_10: f[3], exposure: EXPO_LBL[f[4]],
      risk_score: s.R, risk_band: band(s.R), dependent_services: svcs, category: VNAME[fi.id],
      how_hard: FIXLVL[fi.level][0], call_professional: fi.pro, details: f[6] || null,
      missing_information: typeof missing === "function" ? missing(f, s, svcs) : [] };
    const out = $("aiout"); if (out) out.innerHTML = `<div class="aimeta">The answer is in the "Ask the AI" panel.</div>`;
    ask({ kind: "explain", evidence, checked: fi.id }, `Explain this problem in simple words: ${f[1]}`);
  };

  /* ---------- Coverage tiles: show the problems, with Ask AI next to each ---------- */
  function askAboutFinding(fid) {
    const f = data().findings.find(x => x[0] === fid); if (!f) return;
    const s = score(f), n = node(f[2]);
    const svcs = Object.keys(impact(f[2])).filter(id => node(id).svc).map(id => node(id).name);
    window.askAI(f, s, n, svcs);
  }
  window.renderCoverage = function () {
    const groups = {};
    data().findings.forEach(f => { if (tasks[f[0]]?.status === "ver") return; (groups[classify(f)] = groups[classify(f)] || []).push(f); });
    const present = Object.keys(groups).length, total = Object.values(groups).reduce((a, g) => a + g.length, 0);
    $("covorg").textContent = data().label;
    $("covcount").textContent = `${present} of 15 present · ${total} open problem${total === 1 ? "" : "s"}`;
    $("cov").innerHTML = VCAT.map(([id, name], i) => {
      const list = (groups[id] || []).sort((a, b) => score(b).R - score(a).R);
      const head = `<div class="n">${String(i + 1).padStart(2, "0")}</div><div class="t">${esc(name)}</div>`;
      if (!list.length) return `<div class="cv">${head}<div class="cv-none"><span class="c zero">Monitored, none found</span>
        <button class="cv-what" type="button" data-what="${esc(name)}">What is this?</button></div></div>`;
      return `<div class="cv hit">${head}<div class="c">${list.length} found</div><ul class="cv-list">${list.map(f => {
        const b = band(score(f).R);
        return `<li><button class="cv-prob" type="button" data-show="${esc(f[0])}" title="See how to fix it"><span class="dot d-${b}"></span>${esc(f[1])}</button>
          <button class="cv-ask" type="button" data-ask="${esc(f[0])}" aria-label="Ask AI about: ${esc(f[1])}">Ask AI</button></li>`;
      }).join("")}</ul></div>`;
    }).join("");
  };
  $("cov").addEventListener("click", e => {
    const askEl = e.target.closest("[data-ask]"), show = e.target.closest("[data-show]"), what = e.target.closest("[data-what]");
    if (askEl) return askAboutFinding(askEl.dataset.ask);
    if (show) { sel = show.dataset.show; renderFindings(); renderDetail(); problemsSec.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    if (what) ask({ kind: "chat", question: `In simple words, what is "${what.dataset.what}", why does it matter for a small organization, and how do I protect against it?` },
      `What is "${what.dataset.what}" and how do I protect against it?`);
  });

  let PLAYBOOK = null;
  fetch("/playbook.json").then(r => r.json()).then(j => { PLAYBOOK = j; }).catch(() => {});

  /* ---------- AI model ---------- */
  async function aiCheck() {
    try { const j = await (await fetch("/api/ai-status")).json(); aiReady = !!(j.ok && j.model); }
    catch (e) { aiReady = false; }
    const hintEl = $("modelHint");
    if (!aiReady) hintEl.dataset.off = "1";
    if (!aiReady) hintEl.innerHTML = `<div class="warnnote">The AI helper is not ready on this laptop. Restart with <code>bash start.sh</code>. It starts the AI helper and downloads the security model the first time. Everything else works without it.</div>`;
    else if (hintEl.dataset.off) { delete hintEl.dataset.off; hintEl.innerHTML = ""; loadModels(); }
  }
  async function loadModels() {
    let j;
    try { j = await (await fetch("/api/ai/models")).json(); } catch (e) { return; }
    const s = $("aiModel");
    if (!j.installed.length) { s.innerHTML = `<option>No model downloaded</option>`; s.disabled = true; }
    else {
      s.disabled = false;
      s.innerHTML = j.installed.map(n => `<option value="${esc(n)}"${n === j.current ? " selected" : ""}>${esc(shortModel(n))}</option>`).join("");
    }
    const secm = j.recommended[0];
    if (j.ok && !j.installed.some(n => /foundation-sec/i.test(n)) && !$("modelHint").dataset.off)
      $("modelHint").innerHTML = `<div class="warnnote">For security work we recommend <b>${esc(secm.label)}</b> (${esc(secm.size)}). Download it once in a terminal: <code>ollama pull ${esc(secm.name)}</code>, then refresh this page.</div>`;
  }
  $("aiModel").onchange = async () => {
    const m = $("aiModel").value, msg = $("modelMsg"); msg.hidden = false; msg.textContent = "Switching…";
    try {
      const r = await fetch("/api/ai/model", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: m }) });
      const j = await r.json(); if (!r.ok) throw new Error(j.error);
      msg.textContent = "Now using " + shortModel(m) + ". The first answer will be slower while it loads.";
      if (typeof aiStatus === "function") aiStatus();
    } catch (e) { msg.textContent = e.message; }
  };

  /* ---------- Liquid Glass shell: large title, account capsule, floating navigation ---------- */
  const ICONS = {
    overview: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    servers: '<rect x="3" y="4" width="18" height="7" rx="2.5"/><rect x="3" y="13" width="18" height="7" rx="2.5"/><path d="M7 7.5h.01M7 16.5h.01"/>',
    problems: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    ask: '<path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z"/><path d="M19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2-2.2-.8 2.2-.8z"/>',
    fixes: '<path d="M10 6h10M10 12h10M10 18h10"/><path d="M3.5 6l1.2 1.2L7 5M3.5 12l1.2 1.2L7 11M3.5 18l1.2 1.2L7 17"/>',
    impact: '<circle cx="5" cy="6" r="2.5"/><circle cx="19" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M7.1 7.6l3.8 8.3M16.9 7.6l-3.8 8.3M7.5 6h9"/>',
    coverage: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    security: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    plans: '<rect x="2.5" y="5" width="19" height="14" rx="3"/><path d="M2.5 10h19M6.5 15h4"/>'
  };
  const kpis = document.getElementById("kpis");
  const problemsSec = $("findings").closest("section"); problemsSec.id = "problems";
  const fixesSec = $("tasks").closest("section"); fixesSec.id = "fixes";
  const impactSec = $("graph").closest("section"); impactSec.id = "impact";
  const coverageSec = $("cov").closest("section"); coverageSec.id = "coverage";
  const fixH = fixesSec.querySelector("h2"); if (fixH) fixH.textContent = "Fix list";

  /* ---------- Plans (sample pricing, no payments) ---------- */
  const PLANS = [
    { id: "free", name: "Free", m: 0, limit: 1, tag: "Try it out", feat: ["1 server or PC", "Scan any time", "Simple fix steps", "AI help on your own machine"] },
    { id: "starter", name: "Starter", m: 999, limit: 5, tag: "Small business or school", feat: ["Up to 5 servers or PCs", "“Scan now” from anywhere, plus checks every 6 hours", "AI assistant with web search", "Fix list with proof of each fix", "Email support"] },
    { id: "pro", name: "Professional", m: 3999, limit: 25, tag: "Growing business, college or clinic", popular: true, feat: ["Up to 25 servers or PCs", "Everything in Starter", "Windows and Linux log reading", "Impact map and priorities", "3 team members", "Priority support"] },
    { id: "institutional", name: "Institutional", m: null, limit: null, tag: "Large college or hospital", feat: ["Unlimited servers", "Teams and roles", "Compliance-ready reports", "Help with setup", "Service-level agreement"] }
  ];
  let plan = "free", billing = "monthly", plansUsed = -1;
  const plansSec = document.createElement("section"); plansSec.className = "panel"; plansSec.id = "plans";
  fixesSec.after(plansSec);
  const inr = n => "₹" + n.toLocaleString("en-IN");

  /* ---------- Account & security ---------- */
  const secSec = document.createElement("section"); secSec.className = "panel"; secSec.id = "security";
  plansSec.after(secSec);
  let me = {};
  const post = async (url, body) => {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || "Something went wrong."); return j;
  };
  function loadQR() {
    return window.QRCode ? Promise.resolve() : new Promise((ok, bad) => {
      const sc = document.createElement("script"); sc.src = "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js";
      sc.onload = ok; sc.onerror = bad; document.head.appendChild(sc);
    });
  }
  function renderSecurity(msg) {
    const c = me.contact || {}, age = me.token_created ? Math.floor((Date.now() / 1000 - me.token_created) / 86400) : null;
    secSec.innerHTML = `
      <div class="panel-head"><div><h2>Account &amp; security</h2><div class="muted" style="font-size:13px">Protect this account, choose who to call for serious problems, and control your data.</div></div></div>
      ${msg ? `<div class="rec secmsg" style="margin-bottom:12px">${msg}</div>` : ""}
      <div class="sec-grid">
        <div class="sec-card"><h3>2-step sign-in <span class="pill${me.two_factor ? " on" : ""}">${me.two_factor ? "On" : "Off"}</span></h3>
          <p>After your password, also enter a 6-digit code from an app on your phone (Google Authenticator, Microsoft Authenticator, etc.).</p>
          <div id="tfaBox">${me.two_factor
            ? `<div class="row"><input type="password" id="tfaOffPw" placeholder="Your password" autocomplete="current-password" style="max-width:220px"><button class="btn ghost mini" id="tfaOff" type="button">Turn off</button></div>`
            : `<button class="btn mini" id="tfaOn" type="button">Turn on</button>`}</div></div>
        <div class="sec-card"><h3>Who to call for serious problems</h3>
          <p>Shown on every problem marked “Call a security professional”, so anyone in your team knows who to contact.</p>
          <input id="ctName" placeholder="Name or company" value="${esc(c.name || "")}">
          <div class="row"><input id="ctPhone" placeholder="Phone" value="${esc(c.phone || "")}" style="flex:1;min-width:140px"><input id="ctEmail" placeholder="Email" value="${esc(c.email || "")}" style="flex:1;min-width:160px"></div>
          <div class="row"><button class="btn mini" id="ctSave" type="button">Save contact</button></div></div>
        <div class="sec-card"><h3>Change password</h3>
          <input type="password" id="pwOld" placeholder="Current password" autocomplete="current-password">
          <input type="password" id="pwNew" placeholder="New password (at least 10 characters)" autocomplete="new-password">
          <div class="row"><button class="btn mini" id="pwSave" type="button">Change password</button></div>
          <p>Changing it signs you out on every other device.</p></div>
        <div class="sec-card"><h3>Checker access code</h3>
          <p>${age == null ? "" : `Created ${age === 0 ? "today" : age + " day" + (age === 1 ? "" : "s") + " ago"}. `}${age != null && age > 90 ? "<b>It's over 90 days old. Reset it and re-run the command on your machines.</b>" : "Reset it if a command was shared with someone it shouldn't have been, and at least every 90 days."}</p>
          <div class="row"><button class="btn ghost mini" id="goReset" type="button">Go to reset</button></div></div>
        <div class="sec-card"><h3>Your data</h3>
          <p>Download everything InfraSentinel stores about your organization, or delete it all. See the <a href="/privacy" target="_blank">privacy notice</a>.</p>
          <div class="row"><a class="btn ghost mini" href="/api/account/export" download>Download my data</a></div>
          <div class="row"><input type="password" id="delPw" placeholder="Password to confirm" autocomplete="current-password" style="max-width:220px"><button class="btn stop mini" id="delBtn" type="button">Delete my account</button></div></div>
      </div>`;
    const say = (m) => renderSecurity(m);
    const tOn = $("tfaOn");
    if (tOn) tOn.onclick = async () => {
      try {
        const j = await post("/api/2fa/setup");
        $("tfaBox").innerHTML = `<p>1. In your authenticator app, add an account and scan this code, or type the key below.</p>
          <div id="qr"></div><div class="secret">${esc(j.secret.replace(/(.{4})/g, "$1 ").trim())}</div>
          <p>2. Type the 6-digit code it shows:</p>
          <div class="row"><input id="tfaCode" inputmode="numeric" maxlength="7" placeholder="123 456" style="max-width:140px"><button class="btn mini" id="tfaConfirm" type="button">Confirm</button></div>`;
        loadQR().then(() => new QRCode($("qr"), { text: j.uri, width: 160, height: 160 })).catch(() => { $("qr").remove(); });
        $("tfaConfirm").onclick = async () => {
          try { await post("/api/2fa/enable", { code: $("tfaCode").value }); me.two_factor = true; say("2-step sign-in is on. You'll need your phone next time you sign in."); }
          catch (e) { say(esc(e.message)); }
        };
      } catch (e) { say(esc(e.message)); }
    };
    const tOff = $("tfaOff");
    if (tOff) tOff.onclick = async () => {
      try { await post("/api/2fa/disable", { password: $("tfaOffPw").value }); me.two_factor = false; say("2-step sign-in is off."); } catch (e) { say(esc(e.message)); }
    };
    $("ctSave").onclick = async () => {
      try { const j = await post("/api/contact", { name: $("ctName").value, phone: $("ctPhone").value, email: $("ctEmail").value });
        me.contact = j.contact; say("Contact saved. It now shows on every serious problem."); renderAll(); } catch (e) { say(esc(e.message)); }
    };
    $("pwSave").onclick = async () => {
      try { await post("/api/password", { password: $("pwOld").value, new: $("pwNew").value }); say("Password changed. Other devices were signed out."); }
      catch (e) { say(esc(e.message)); }
    };
    $("goReset").onclick = () => { showSteps(true); $("resetTok").scrollIntoView({ behavior: "smooth", block: "center" }); };
    let delArm = false;
    $("delBtn").onclick = async () => {
      if (!delArm) { delArm = true; $("delBtn").textContent = "This deletes everything. Click again"; setTimeout(() => { delArm = false; const b = $("delBtn"); if (b) b.textContent = "Delete my account"; }, 6000); return; }
      try { await post("/api/account/delete", { password: $("delPw").value }); location.replace("/login"); } catch (e) { say(esc(e.message)); }
    };
  }
  function decoratePro() {
    const c = me.contact || {};
    document.querySelectorAll(".probanner").forEach(b => {
      if (b.querySelector(".procontact")) return;
      const el = document.createElement("span"); el.className = "procontact";
      el.innerHTML = c.name || c.phone || c.email
        ? `Your contact: ${esc(c.name || "")}${c.phone ? ` · <a href="tel:${esc(c.phone)}">${esc(c.phone)}</a>` : ""}${c.email ? ` · <a href="mailto:${esc(c.email)}">${esc(c.email)}</a>` : ""}`
        : `No contact saved yet. Add one under Account &amp; security.`;
      b.appendChild(el);
    });
  }
  function renderPlans(msg) {
    const used = SECTORS.mine ? SECTORS.mine.nodes.filter(n => n[2] === 0).length : 0;
    const cur = PLANS.find(p => p.id === plan) || PLANS[0];
    const pct = cur.limit ? Math.min(100, Math.round(used / cur.limit * 100)) : 0;
    plansSec.innerHTML = `
      <div class="panel-head"><div><h2>Plans</h2><div class="muted" style="font-size:13px">Sample pricing for demonstration. No payment is taken and no card details are asked for.</div></div>
        <div class="seg" id="billSeg" role="group" aria-label="Billing period"><button type="button" data-b="monthly" aria-pressed="${billing === "monthly"}">Monthly</button><button type="button" data-b="yearly" aria-pressed="${billing === "yearly"}">Yearly · 2 months free</button></div></div>
      <div class="usage"><div><b>${cur.name} plan</b><span class="muted"> · ${used} of ${cur.limit ?? "unlimited"} server${cur.limit === 1 ? "" : "s"} used</span></div>
        <div class="ubar"><span style="width:${pct}%" class="${pct >= 100 ? "full" : ""}"></span></div>${cur.limit && used > cur.limit ? `<div class="muted" style="font-size:12px">You're over this plan's limit. In a real launch you'd be asked to upgrade.</div>` : ""}</div>
      <div class="plans">${PLANS.map(p => {
        const price = p.m === null ? "Custom" : p.m === 0 ? "₹0" : billing === "yearly" ? inr(p.m * 10) : inr(p.m);
        const per = p.m === null ? "talk to us" : p.m === 0 ? "forever" : billing === "yearly" ? "per year" : "per month";
        const isCur = p.id === plan;
        return `<div class="plan${p.popular ? " pop" : ""}${isCur ? " cur" : ""}">
          ${p.popular ? `<span class="plan-badge">Most popular</span>` : ""}
          <div class="plan-name">${p.name}</div><div class="muted plan-tag">${p.tag}</div>
          <div class="plan-price">${price}<small>${per}</small></div>
          <ul>${p.feat.map(f => `<li>${f}</li>`).join("")}</ul>
          ${isCur ? `<button class="btn ghost" type="button" disabled>Current plan</button>` :
            p.m === null ? `<button class="btn ghost" type="button" data-talk="1">Talk to us</button>` :
            `<button class="btn${p.popular ? "" : " ghost"}" type="button" data-plan="${p.id}">Choose ${p.name}</button>`}
        </div>`; }).join("")}</div>
      <div id="planMsg">${msg ? `<div class="rec" style="margin-top:14px">${msg}</div>` : ""}</div>`;
    plansSec.querySelectorAll("#billSeg button").forEach(b => b.onclick = () => { billing = b.dataset.b; renderPlans(); });
    plansSec.querySelectorAll("button[data-plan]").forEach(b => b.onclick = async () => {
      b.disabled = true; b.textContent = "Switching…";
      try {
        const r = await fetch("/api/plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan: b.dataset.plan, billing }) });
        const j = await r.json(); if (!r.ok) throw new Error(j.error);
        plan = j.plan; billing = j.billing;
        renderPlans(`You're now on the <b>${PLANS.find(p => p.id === plan).name}</b> plan (${billing}). This is a sample: nothing was charged.`);
      } catch (e) { renderPlans(esc(e.message || "Couldn't change plan.")); }
    });
    plansSec.querySelectorAll("button[data-talk]").forEach(b => b.onclick = () =>
      renderPlans("Institutional plans are set up with each organization. In a real launch this would open a contact form."));
  }
  wrap.insertBefore(kpis, sec);          // Overview first, then servers, problems, the assistant
  sec.after(problemsSec); problemsSec.after(asst);
  const scrollCss = document.createElement("style");
  scrollCss.textContent = "section,#kpis{scroll-margin-top:20px}";
  document.head.appendChild(scrollCss);

  // Large title with today's date, like iOS
  const brand = header.querySelector(".brand"), h1 = brand.querySelector("h1"), sub = h1.nextElementSibling;
  const dateEl = document.createElement("div"); dateEl.className = "is-date";
  dateEl.textContent = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
  h1.parentNode.insertBefore(dateEl, h1);
  h1.textContent = "Overview";
  if (sub) sub.textContent = "Your organization's security, in plain language.";
  const right = header.lastElementChild;
  const acct = document.createElement("div"); acct.className = "is-acct";
  acct.innerHTML = `<span class="is-avatar" id="isAvatar">·</span><span class="is-who"><b id="isWho">Signed in</b><small id="isOrg"></small></span><button class="linkbtn" id="isSignout" type="button">Sign out</button>`;
  const headRow = document.createElement("div"); headRow.className = "is-headrow";
  const themeBtn = document.createElement("button"); themeBtn.type = "button"; themeBtn.className = "is-theme"; themeBtn.id = "themeBtn";
  headRow.append(themeBtn, acct); right.insertBefore(headRow, right.firstChild);
  const SUN = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z"/></svg>';
  const isDark = () => (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
  function paintThemeBtn() {
    const d = isDark(); themeBtn.innerHTML = d ? SUN : MOON;
    themeBtn.setAttribute("aria-label", d ? "Switch to light theme" : "Switch to dark theme"); themeBtn.title = themeBtn.getAttribute("aria-label");
  }
  themeBtn.onclick = () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("is_theme", next); } catch (e) {}
    paintThemeBtn(); if (typeof renderGraph === "function") renderGraph();
  };
  paintThemeBtn();
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", paintThemeBtn);
  const tools = right.querySelector("#scanBtn")?.parentElement; if (tools) tools.classList.add("is-toolbar");

  // Floating navigation
  const NAV = [
    { group: "Monitor" },
    { id: "overview", label: "Overview", target: () => kpis },
    { id: "servers", label: "Servers", target: () => sec },
    { id: "problems", label: "Problems", target: () => problemsSec, badge: true },
    { group: "Assist" },
    { id: "ask", label: "Ask AI", target: () => asst },
    { id: "fixes", label: "Fixes", target: () => fixesSec },
    { group: "Analyze" },
    { id: "impact", label: "Impact map", target: () => impactSec, full: true },
    { id: "coverage", label: "Coverage", target: () => coverageSec, full: true },
    { group: "Account" },
    { id: "plans", label: "Plans", target: () => plansSec },
    { id: "security", label: "Security", target: () => secSec }
  ];
  const nav = document.createElement("nav"); nav.className = "is-nav"; nav.setAttribute("aria-label", "Sections");
  nav.innerHTML = `<div class="is-brand"><span class="is-logo"><svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="#fff" stroke-width="2.2"><path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z"/><circle cx="12" cy="11" r="2.4" fill="#fff"/></svg></span><b>InfraSentinel</b></div>` +
    NAV.map(n => n.group ? `<div class="is-group" data-g="${n.group}">${n.group}</div>` :
      `<button class="is-item" type="button" data-nav="${n.id}"><svg viewBox="0 0 24 24">${ICONS[n.id === "ask" ? "ask" : n.id]}</svg><span>${n.label}</span>${n.badge ? `<span class="is-badge" id="isBadge" hidden>0</span>` : ""}${n.full ? `<span class="is-full">Full</span>` : ""}</button>`).join("") +
    `<div class="is-foot"><label class="advtog" for="advOn"><input type="checkbox" id="advOn"><span class="tog"></span><span><b>Advanced</b><small>Map, scoring, samples</small></span></label></div>`;
  document.body.appendChild(nav);
  nav.querySelectorAll(".is-item").forEach(b => b.onclick = () => {
    const n = NAV.find(x => x.id === b.dataset.nav);
    if (n.full && typeof setMode === "function" && MODE !== "full") setMode("full");
    requestAnimationFrame(() => {
      if (n.id === "overview") window.scrollTo({ top: 0, behavior: "smooth" });
      else n.target().scrollIntoView({ behavior: "smooth", block: "start" });
    });
    setCurrent(n.id);
  });
  function setCurrent(id) { nav.querySelectorAll(".is-item").forEach(b => b.setAttribute("aria-current", String(b.dataset.nav === id))); }
  setCurrent("overview");
  const io = new IntersectionObserver(entries => {
    const vis = entries.filter(e => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
    if (!vis) return;
    const n = NAV.find(x => x.target && x.target() === vis.target); if (n) setCurrent(n.id);
  }, { rootMargin: "-25% 0px -65% 0px" });
  NAV.filter(n => n.target).forEach(n => io.observe(n.target()));

  // Keep the Problems badge in step with the current organization
  const baseRenderAll = window.renderAll;
  window.renderAll = function () {
    if (MODE !== "full" && SECTORS.mine && cur !== "mine") { cur = "mine"; sel = null; sim = null; initTasks(); }
    baseRenderAll();
    const open = data().findings.filter(f => tasks[f[0]]?.status !== "ver").length;
    const b = $("isBadge"); if (b) { b.textContent = open; b.hidden = !open; }
    document.body.classList.toggle("no-servers", MODE !== "full" && !SECTORS.mine);
    const adv = $("advOn"); if (adv) adv.checked = MODE === "full";
    const usedNow = SECTORS.mine ? SECTORS.mine.nodes.filter(n => n[2] === 0).length : 0;
    if (!plansSec.querySelector(".plans") || usedNow !== plansUsed) { plansUsed = usedNow; renderPlans(); }
    decoratePro();
  };
  const baseRenderDetail = window.renderDetail;
  if (typeof baseRenderDetail === "function") window.renderDetail = function () { baseRenderDetail(); decoratePro(); };

  // Plain overview numbers in the everyday view; the detailed tiles stay in Advanced
  const baseKPIs = window.renderKPIs;
  window.renderKPIs = function () {
    if (MODE === "full") return baseKPIs();
    const f = data().findings, open = f.filter(x => tasks[x[0]]?.status !== "ver");
    const serious = open.filter(x => score(x).R >= 60).length;
    const nServers = data().nodes.filter(n => n[2] === 0).length;
    const tile = (label, v, sub, cls) => `<div class="kpi"><div class="eyebrow">${label}</div><div class="v ${cls || ""}">${v}</div><div class="muted" style="font-size:12px">${sub}</div></div>`;
    $("kpis").innerHTML =
      tile("Problems to fix", open.length, `on ${nServers} server${nServers === 1 ? "" : "s"}`) +
      tile("Serious", serious, serious ? "fix these first" : "nothing urgent", serious ? "is-bad" : "is-good") +
      tile("Fixed", f.length - open.length + (cur === "mine" ? verifiedCount : 0), cur === "mine" && verifiedCount ? "confirmed by re-scan" : "with proof recorded", "is-good");
  };
  const baseSetMode = window.setMode;
  window.setMode = function (m) { baseSetMode(m); renderAll(); };
  $("advOn").onchange = () => setMode($("advOn").checked ? "full" : "simple");

  // Never show a cached copy of someone's dashboard (Back button after signing out or switching account)
  addEventListener("pageshow", e => { if (e.persisted) location.reload(); });
  let shownAs = null;
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState !== "visible" || !shownAs) return;
    try { const r = await fetch("/api/me", { cache: "no-store" });
      if (r.status === 401) return location.replace("/login");
      const m = await r.json(); if (m.email !== shownAs) location.reload(); } catch (e) {}
  });

  /* ---------- start ---------- */
  (async function start() {
    const r = await fetch("/api/me");
    if (r.status === 401) return (location.replace("/login"));
    me = await r.json(); shownAs = me.email; renderSecurity();
    try { const c = await (await fetch("/api/config", { cache: "no-store" })).json(); if (Array.isArray(c.weights)) W = c.weights; } catch (e) {}
    plan = me.plan || "free"; billing = me.billing || "monthly"; renderPlans();
    bar.innerHTML = `<span>Signed in as <b>${esc(me.email)}</b> · ${esc(me.org || "")}</span><button class="linkbtn" id="signout" type="button">Sign out</button>`;
    const out = async () => { await fetch("/api/logout", { method: "POST" }); location.replace("/login"); };
    $("signout").onclick = out; $("isSignout").onclick = out;
    $("isWho").textContent = me.org || "Your organization";
    $("isOrg").textContent = me.email;
    $("isAvatar").textContent = (me.org || me.email || "?").split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
    const hr = new Date().getHours();
    if (sub) sub.textContent = `Good ${hr < 12 ? "morning" : hr < 17 ? "afternoon" : "evening"}, ${me.org || "there"}.`;
    await poll();
    if (!SECTORS.mine) showSteps(true);
    await aiCheck(); loadModels();
    setInterval(poll, 6000);
    setInterval(aiCheck, 20000);
  })();
})();
