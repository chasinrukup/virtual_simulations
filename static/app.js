/* ── State ──────────────────────────────────────────────────────────────── */
let scenarios        = [];
let selectedScenario = null;
let logOffset        = 0;
let pollTimer        = null;

// Ping test auto-trigger state
let _pingTestTriggered = false;
let _prevStatus        = null;

/* ── Init ────────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  loadScenarios();
  startPolling();
});

/* ── Scenarios ───────────────────────────────────────────────────────────── */
async function loadScenarios() {
  const res  = await fetch("/api/scenarios");
  scenarios  = await res.json();
  renderScenarios();
}

function renderScenarios() {
  const el = document.getElementById("scenarioList");
  el.innerHTML = "";

  scenarios.forEach(s => {
    const card = document.createElement("div");
    card.className = "scenario-card" + (s.available ? "" : " unavailable");
    card.innerHTML = `
      <div class="scenario-header" onclick="toggleCard(${s.id})">
        <span class="scenario-name">${s.id + 1}. ${s.name}</span>
        <span class="scenario-badge ${s.available ? "ok" : "na"}">
          ${s.available ? "Ready" : "Missing"}
        </span>
      </div>
      <div class="scenario-body">
        <div class="scenario-desc">${s.description}</div>
        <div class="scenario-layout">${s.layout}</div>
        <div class="scenario-meta">
          <span>&#9632; ${s.subnets.length} subnet${s.subnets.length !== 1 ? "s" : ""}</span>
          <span>&#9632; ${s.vm_count} VMs</span>
          <span>&#9632; ${s.firewall_count} firewall${s.firewall_count !== 1 ? "s" : ""}</span>
        </div>
        ${s.missing.length ? `<div class="scenario-missing">Missing: ${s.missing.join(", ")}</div>` : ""}
        <button class="btn btn-primary" style="width:100%"
          onclick="openDeployModal(${s.id})"
          ${s.available ? "" : "disabled"}>
          Deploy
        </button>
      </div>`;
    el.appendChild(card);
  });
}

function toggleCard(id) {
  const cards = document.querySelectorAll(".scenario-card");
  cards[id].classList.toggle("open");
}

/* ── Deploy modal ────────────────────────────────────────────────────────── */
function openDeployModal(id) {
  selectedScenario = id;
  const s = scenarios[id];
  document.getElementById("modalTitle").textContent = `Deploy: ${s.name}`;
  document.getElementById("modalBody").textContent  =
    `${s.description}\n\nTopology:\n${s.layout}\n\nSubnets: ${s.subnets.join(", ")}\nVMs: ${s.vm_count}   Firewalls: ${s.firewall_count}`;
  document.getElementById("deployModal").style.display = "flex";
}

function closeModal() {
  document.getElementById("deployModal").style.display = "none";
  selectedScenario = null;
}

async function confirmDeploy() {
  if (selectedScenario === null) return;
  const scenarioId = selectedScenario;   // save before closeModal() clears it
  closeModal();
  _pingTestTriggered = false;
  _prevStatus        = null;
  logOffset = 0;
  document.getElementById("logOutput").innerHTML = "";

  const res = await fetch("/api/deploy", {
    method:  "POST",
    headers: {"Content-Type": "application/json"},
    body:    JSON.stringify({scenario_id: scenarioId}),
  });
  const data = await res.json();
  if (!res.ok) {
    appendLog("ERROR: " + (data.error || "Deploy failed"), "log-err");
  }
}

/* ── Polling ─────────────────────────────────────────────────────────────── */
function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(poll, 2000);
  poll();
}

async function poll() {
  await Promise.all([pollLog(), pollStatus()]);
}

/* ── Log polling ─────────────────────────────────────────────────────────── */
// Lines that are raw VBoxManage noise — hide them from the UI
function isNoisyLine(line) {
  const t = line.trim();
  if (t.startsWith("VBoxManage "))  return true;
  if (t.startsWith("stdout:"))      return true;
  if (t.startsWith("stderr:"))      return true;
  if (t.startsWith("DEBUG"))        return true;
  return false;
}

async function pollLog() {
  try {
    const res  = await fetch(`/api/log?since=${logOffset}`);
    const data = await res.json();
    updateStatusIndicator(data.status, data.scenario);

    data.lines.forEach(line => {
      if (isNoisyLine(line)) return;
      const cls = classifyLine(line);
      appendLog(line, cls);
    });
    logOffset = data.total;
  } catch (_) {}
}

function classifyLine(line) {
  if (line.includes("[OK]") || line.includes("COMPLETE")) return "log-ok";
  if (line.includes("ERROR") || line.includes("FAIL"))    return "log-err";
  if (line.startsWith("===") || line.startsWith("  ===")) return "log-head";
  return "log-info";
}

function appendLog(text, cls = "log-info") {
  const el   = document.getElementById("logOutput");
  const line = document.createElement("div");
  line.className = cls;
  line.textContent = text;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

function clearLog() {
  document.getElementById("logOutput").innerHTML = "";
  logOffset = 0;
}

function copyLog() {
  const el   = document.getElementById("logOutput");
  const text = [...el.children].map(c => c.textContent).join("\n");
  if (!text.trim()) return;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("btnCopyLog");
    const orig = btn.textContent;
    btn.textContent = "✓ Copied";
    setTimeout(() => btn.textContent = orig, 1800);
  });
}

/* ── Status polling ──────────────────────────────────────────────────────── */
async function pollStatus() {
  try {
    const res  = await fetch("/api/status");
    const data = await res.json();
    renderTopology(data);
    renderVmTable(data);
    updateControls(data);

    // Auto-trigger ping test once when a pre-built lab transitions to running
    if (data.is_prebuilt && data.status === "running" && _prevStatus === "deploying"
        && !_pingTestTriggered) {
      _pingTestTriggered = true;
      appendLog("Auto-ping test will run in 90 seconds (waiting for VMs to finish booting)…", "log-info");
      setTimeout(() => runPingTest(), 90000);
    }
    if (data.status === "idle" || data.status === "stopping") {
      _pingTestTriggered = false;
    }
    _prevStatus = data.status;
  } catch (_) {}
}

/* ── Status indicator ────────────────────────────────────────────────────── */
function updateStatusIndicator(status, scenario) {
  const dot  = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  dot.className = "status-dot " + (status || "idle");
  const labels = {
    idle:      "Idle",
    deploying: scenario ? `Deploying: ${scenario}` : "Deploying...",
    running:   scenario ? `Running: ${scenario}`   : "Running",
    stopping:  "Stopping...",
    stopped:   "Stopped",
  };
  text.textContent = labels[status] || status;
}

/* ── Topology renderer ───────────────────────────────────────────────────── */
function subnetColorClass(name) {
  const n = name.toUpperCase();
  if (n === "WAN")  return "subnet-wan";
  if (n === "LAN")  return "subnet-lan";
  if (n === "DMZ")  return "subnet-dmz";
  if (n === "MGMT") return "subnet-mgmt";
  return "subnet-other";
}

function stateColor(state) {
  if (state === "running")  return "#34d399";
  if (state === "poweroff") return "#4b5563";
  return "#fbbf24";
}

function renderTopology(data) {
  const el = document.getElementById("topologyView");
  if (!data.subnets || data.subnets.length === 0) {
    el.className = "topology-empty";
    el.textContent = "Select a scenario and click Deploy to begin.";
    return;
  }

  const fwNames = new Set((data.firewalls || []).map(f => f.vm_name));

  // Group endpoint VMs by subnet
  const subnetVMs = {};
  data.subnets.forEach(s => { subnetVMs[s.name] = []; });
  (data.vms || []).forEach(vm => {
    if (fwNames.has(vm.name)) return;
    vm.subnets.forEach(sn => {
      if (subnetVMs[sn]) subnetVMs[sn].push(vm);
    });
  });

  el.className = "";
  const diag = document.createElement("div");
  diag.className = "topology-diagram";

  data.subnets.forEach((subnet, idx) => {
    // Firewall connector between adjacent subnets
    if (idx > 0) {
      const prev = data.subnets[idx - 1];
      const fw   = (data.firewalls || []).find(f => {
        const all = [f.wan, ...f.lan];
        return all.includes(prev.name) && all.includes(subnet.name);
      });
      const conn = document.createElement("div");
      conn.className = "topo-connector";
      if (fw) {
        const fwVm  = (data.vms || []).find(v => v.name === fw.vm_name);
        const fwCol = stateColor(fwVm ? fwVm.state : "unknown");
        const canSsh = fwVm && fwVm.state === "running";
        conn.innerHTML = `
          <div class="topo-line"></div>
          <div class="topo-fw-box${canSsh ? " topo-fw-clickable" : ""}"
               ${canSsh ? `onclick="openSshDialog('${fw.vm_name}')"` : ""}
               title="${fw.vm_name}${canSsh ? " — click to SSH" : ""}">
            <div class="topo-fw-label">
              <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${fwCol};margin-right:4px;vertical-align:middle"></span>
              &#9650; ${fw.vm_name}
            </div>
            <div class="topo-fw-sub">${fw.wan} ↔ ${fw.lan.join(", ")}</div>
          </div>
          <div class="topo-line"></div>`;
      } else {
        conn.innerHTML = `<div class="topo-line" style="width:40px"></div>`;
      }
      diag.appendChild(conn);
    }

    // VM group for this subnet
    const group = document.createElement("div");
    group.className = "topo-vm-group";

    const vms = subnetVMs[subnet.name] || [];
    const tag  = `<div class="topo-subnet-tag ${subnetColorClass(subnet.name)}">${subnet.name}</div>`;

    if (vms.length === 0) {
      group.innerHTML = tag + `<div class="topo-empty-slot">no VMs</div>`;
    } else {
      const cards = vms.map(vm => {
        const col      = stateColor(vm.state);
        const canClick = vm.state === "running";
        const isKali   = vm.is_kali;
        const action   = isKali ? `openDesktop('${vm.name}')` : `openSshDialog('${vm.name}')`;
        const badge    = isKali ? '<span class="topo-vm-ssh">VNC</span>' : '<span class="topo-vm-ssh">SSH</span>';
        const tip      = isKali ? " (click for desktop)" : " (click to SSH)";
        return `<div class="topo-vm-card${canClick ? " topo-vm-clickable" : ""}"
                     ${canClick ? `onclick="${action}"` : ""}
                     title="${vm.name} — ${vm.state}${canClick ? tip : ""}">
          <div class="topo-vm-dot" style="background:${col}"></div>
          <span class="topo-vm-name">${vm.name}</span>
          ${canClick ? badge : ""}
        </div>`;
      }).join("");
      group.innerHTML = tag + cards;
    }
    diag.appendChild(group);
  });

  el.innerHTML = "";
  el.appendChild(diag);
}

/* ── VM status table ─────────────────────────────────────────────────────── */
function renderVmTable(data) {
  const el = document.getElementById("vmStatus");
  if (!data.vms || data.vms.length === 0) {
    el.className = "vm-status-empty";
    el.textContent = "No lab deployed.";
    return;
  }

  el.className = "";
  const fwNames = new Set((data.firewalls || []).map(f => f.vm_name));

  // Build subnet DHCP range lookup
  const subnetRanges = {};
  (data.subnets || []).forEach(s => {
    if (s.dhcp_start && s.dhcp_end)
      subnetRanges[s.name] = `${s.dhcp_start} – ${s.dhcp_end}`;
  });

  const rows = data.vms.map(vm => {
    const isfw   = fwNames.has(vm.name);
    const stCls  = vm.state === "running"  ? "state-running"
                 : vm.state === "poweroff" ? "state-poweroff" : "state-other";
    const rolCls = isfw ? "role-badge role-firewall" : "role-badge";
    const roleLabel = isfw ? "firewall" : vm.role;
    const subnets = vm.subnets.join(", ");

    // SSH info cell
    let sshHtml = "";
    if (!isfw && vm.ssh_user) {
      const range = vm.subnets.map(s => subnetRanges[s]).filter(Boolean).join(" / ") || "see subnet";
      const note  = vm.ssh_note ? `<div class="ssh-note">${vm.ssh_note}</div>` : "";
      sshHtml = `
        <div class="ssh-info">
          <div class="ssh-cmd">ssh ${vm.ssh_user}@<span class="ssh-range">[${range}]</span></div>
          <div class="ssh-pass">pass: <code>${vm.ssh_pass}</code></div>
          ${note}
        </div>`;
    } else if (isfw && vm.ssh_user) {
      const note  = vm.ssh_note ? `<div class="ssh-note">${vm.ssh_note}</div>` : "";
      sshHtml = `<div class="ssh-info"><div class="ssh-pass">user: <code>${vm.ssh_user}</code> / pass: <code>${vm.ssh_pass}</code></div>${note}</div>`;
    }
    if (vm.state === "running") {
      if (vm.is_kali) {
        sshHtml += `<button class="btn btn-primary ssh-term-btn" onclick="openDesktop('${vm.name}')">🖥 Desktop</button>`;
      } else {
        sshHtml += `<button class="btn btn-primary ssh-term-btn" onclick="openSshDialog('${vm.name}')">⬢ Terminal</button>`;
      }
    } else if (!sshHtml) {
      sshHtml = "<span class=\"ssh-na\">—</span>";
    }

    return `<tr>
      <td>${vm.name}</td>
      <td><span class="${rolCls}">${roleLabel}</span></td>
      <td>${subnets}</td>
      <td><span class="state-badge ${stCls}">&#9679; ${vm.state}</span></td>
      <td>${sshHtml}</td>
    </tr>`;
  }).join("");

  el.innerHTML = `
    <table class="vm-table">
      <thead><tr>
        <th>Name</th><th>Role</th><th>Subnets</th><th>State</th><th>SSH Access</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ── Control buttons ─────────────────────────────────────────────────────── */
function updateControls(data) {
  const hasLab    = data.vms && data.vms.length > 0;
  const isRunning = data.status === "running";
  const isBusy    = data.status === "deploying" || data.status === "stopping";

  document.getElementById("btnStop").disabled     = !hasLab || isBusy;
  document.getElementById("btnDelete").disabled   = !hasLab || isBusy;
  document.getElementById("btnPingTest").disabled = !isRunning || !data.is_prebuilt;
}

async function runPingTest() {
  const res = await fetch("/api/ping-test", {method: "POST"});
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    appendLog("Ping test error: " + (d.error || res.statusText), "log-err");
  }
  // Results stream into the log automatically via /api/log polling
}

async function stopAll() {
  if (!confirm("Stop all running VMs?")) return;
  await fetch("/api/stop", {method: "POST"});
}

async function teardown() {
  if (!confirm("Stop and DELETE all VMs in this lab?")) return;
  await fetch("/api/teardown", {method: "POST"});
}

/* ── SSH Dialog ──────────────────────────────────────────────────────────── */

let _sshVm = null;

async function openSshDialog(vmName) {
  _sshVm = vmName;
  document.getElementById("sshDialogTitle").textContent = `SSH: ${vmName}`;
  document.getElementById("sshIp").value    = "";
  document.getElementById("sshUser").value  = "";
  document.getElementById("sshPass").value  = "";
  document.getElementById("sshIpHint").textContent = "Looking up IP address…";
  document.getElementById("sshConnectBtn").disabled = true;
  document.getElementById("sshDialog").style.display = "flex";

  try {
    const res  = await fetch(`/api/vm-ip/${encodeURIComponent(vmName)}`);
    const data = await res.json();

    document.getElementById("sshUser").value = data.ssh_user || "john";
    document.getElementById("sshPass").value = data.ssh_pass || "admin";

    if (data.ip) {
      document.getElementById("sshIp").value = data.ip;
      document.getElementById("sshIpHint").textContent = "✓ IP found automatically";
      document.getElementById("sshIpHint").style.color = "var(--green)";
    } else {
      const rangeHint = data.hint ? ` Expected range: ${data.hint}` : "";
      document.getElementById("sshIpHint").textContent =
        `VM may still be booting — wait 30 s and try again, or enter IP manually.${rangeHint}`;
      document.getElementById("sshIpHint").style.color = "var(--yellow)";
    }
    if (data.ssh_note) {
      document.getElementById("sshIpHint").textContent += `\n⚠ ${data.ssh_note}`;
    }
  } catch (e) {
    document.getElementById("sshIpHint").textContent = "Could not look up IP — enter manually.";
    document.getElementById("sshIpHint").style.color = "var(--muted)";
  }

  document.getElementById("sshConnectBtn").disabled = false;
}

function closeSshDialog() {
  document.getElementById("sshDialog").style.display = "none";
}

function connectSsh() {
  const ip   = document.getElementById("sshIp").value.trim();
  const user = document.getElementById("sshUser").value.trim() || "john";
  const pass = document.getElementById("sshPass").value;
  if (!ip) { alert("Enter an IP address."); return; }
  closeSshDialog();
  _openTerminal(_sshVm, ip, user, pass);
}

/* ── SSH Terminal (polling) ──────────────────────────────────────────────── */

let _term      = null;
let _fitAddon  = null;
let _sid       = null;
let _pollTimer = null;

function _openTerminal(vmName, ip, user, pass) {
  document.getElementById("sshTermTitle").textContent  = `${vmName}  —  ${user}@${ip}`;
  document.getElementById("sshTermStatus").textContent = "Connecting…";
  document.getElementById("sshTermStatus").style.color = "var(--yellow)";
  document.getElementById("sshTermModal").style.display = "flex";

  const termDiv = document.getElementById("termDiv");
  termDiv.innerHTML = "";

  _term = new Terminal({
    cursorBlink: true,
    fontSize:    13,
    fontFamily:  '"Cascadia Code", "Fira Code", Consolas, monospace',
    scrollback:  2000,
    theme: {
      background: "#0f1117", foreground: "#e2e8f0",
      cursor: "#4f8ef7", black: "#1a1d27", brightBlack: "#4b5563",
    },
  });
  _fitAddon = new FitAddon.FitAddon();
  _term.loadAddon(_fitAddon);
  _term.open(termDiv);
  _fitAddon.fit();

  // Start SSH session on server
  fetch("/api/ssh/start", {
    method:  "POST",
    headers: {"Content-Type": "application/json"},
    body:    JSON.stringify({ip, user, pass, cols: _term.cols, rows: _term.rows}),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      _term.write(`\r\n\x1b[31mSSH Error: ${data.error}\x1b[0m\r\n`);
      document.getElementById("sshTermStatus").textContent = "Failed";
      document.getElementById("sshTermStatus").style.color = "var(--red)";
      return;
    }
    _sid = data.sid;
    document.getElementById("sshTermStatus").textContent = "Connected";
    document.getElementById("sshTermStatus").style.color = "var(--green)";

    // Poll for output every 50ms
    _pollTimer = setInterval(_pollSsh, 50);

    // Send keystrokes
    _term.onData(keyData => {
      if (_sid) {
        fetch(`/api/ssh/write/${_sid}`, {method: "POST", body: keyData});
      }
    });

    // Resize
    const ro = new ResizeObserver(() => {
      _fitAddon.fit();
      if (_sid) {
        fetch(`/api/ssh/resize/${_sid}`, {
          method:  "POST",
          headers: {"Content-Type": "application/json"},
          body:    JSON.stringify({cols: _term.cols, rows: _term.rows}),
        });
      }
    });
    ro.observe(termDiv);
  })
  .catch(e => {
    _term.write(`\r\n\x1b[31mCould not start session: ${e}\x1b[0m\r\n`);
  });
}

async function _pollSsh() {
  if (!_sid) return;
  try {
    const res  = await fetch(`/api/ssh/read/${_sid}`);
    const data = await res.json();
    if (data.data)  _term.write(data.data);
    if (!data.alive) {
      _term.write("\r\n\x1b[33m[Session closed]\x1b[0m\r\n");
      document.getElementById("sshTermStatus").textContent = "Closed";
      document.getElementById("sshTermStatus").style.color = "var(--muted)";
      clearInterval(_pollTimer);
      _pollTimer = null;
      _sid = null;
    }
  } catch (_) {}
}

function closeSshTerminal() {
  clearInterval(_pollTimer); _pollTimer = null;
  if (_sid) { fetch(`/api/ssh/close/${_sid}`, {method: "POST"}); _sid = null; }
  if (_term) { _term.dispose(); _term = null; }
  document.getElementById("sshTermModal").style.display = "none";
}

/* ── Kali Desktop (noVNC) ────────────────────────────────────────────────── */

let _desktopVm = null;

async function openDesktop(vmName) {
  _desktopVm = vmName;
  document.getElementById("desktopTitle").textContent  = `Desktop: ${vmName}`;
  document.getElementById("desktopStatus").textContent = "Starting desktop session…";
  document.getElementById("desktopStatus").style.color = "var(--yellow)";
  document.getElementById("desktopCanvas").innerHTML   = "";
  document.getElementById("desktopModal").style.display = "flex";

  let data;
  try {
    const res = await fetch(`/api/vm-desktop/${encodeURIComponent(vmName)}`);
    data = await res.json();
    if (!res.ok) throw new Error(data.error || "Server error");
  } catch (e) {
    document.getElementById("desktopStatus").textContent = String(e);
    document.getElementById("desktopStatus").style.color = "var(--red)";
    return;
  }

  if (typeof window._startNoVNC === "function") {
    window._startNoVNC(data.ws_port, "desktopCanvas");
  } else {
    document.getElementById("desktopStatus").textContent =
      "noVNC not loaded yet — try again in a moment.";
    document.getElementById("desktopStatus").style.color = "var(--red)";
  }
}

function closeDesktop() {
  if (typeof window._stopNoVNC === "function") window._stopNoVNC();
  document.getElementById("desktopModal").style.display = "none";
  if (_desktopVm) {
    fetch("/api/vm-desktop-stop", {
      method:  "POST",
      headers: {"Content-Type": "application/json"},
      body:    JSON.stringify({vm_name: _desktopVm}),
    });
    _desktopVm = null;
  }
}

/* ── Custom Lab Wizard ───────────────────────────────────────────────────── */

const SUBNET_PRESETS = {
  WAN:  {name:"WAN",  base:"192.168.30", color:"subnet-wan"},
  LAN:  {name:"LAN",  base:"192.168.40", color:"subnet-lan"},
  DMZ:  {name:"DMZ",  base:"192.168.50", color:"subnet-dmz"},
  MGMT: {name:"MGMT", base:"192.168.60", color:"subnet-mgmt"},
  DEV:  {name:"DEV",  base:"192.168.70", color:"subnet-other"},
};

// Custom base IPs for non-preset subnets (sequential after presets)
const CUSTOM_BASES = ["192.168.80","192.168.90","192.168.100","192.168.110","192.168.120"];

let wState = {
  step:    1,
  subnets: [],   // {name, preset, base, color}
  vms:     [],   // {name, role, image_filename, image_type, ostype, subnets}
  images:  [],   // from /api/images
};

async function openCustomWizard() {
  wState = {step:1, subnets:[], vms:[], images:[]};
  const res = await fetch("/api/images");
  wState.images = await res.json();
  wRenderStep();
  document.getElementById("customModal").style.display = "flex";
}

function closeCustomWizard() {
  document.getElementById("customModal").style.display = "none";
}

/* ── Step navigation ─────────────────────────────────────────────────────── */

function wNext() {
  if (wState.step === 1) {
    if (wState.subnets.length < 1) { alert("Add at least one subnet."); return; }
    wState.step = 2;
  } else if (wState.step === 2) {
    if (wState.vms.length < 1) { alert("Add at least one VM."); return; }
    wState.step = 3;
  } else if (wState.step === 3) {
    wDeploy();
    return;
  }
  wRenderStep();
}

function wBack() {
  if (wState.step > 1) { wState.step--; wRenderStep(); }
}

function wRenderStep() {
  [1,2,3].forEach(n => {
    document.getElementById(`wStep${n}`).style.display = wState.step === n ? "" : "none";
    const bar = document.getElementById(`wbar${n}`);
    bar.className = "wizard-bar-step" + (wState.step === n ? " active" : wState.step > n ? " done" : "");
  });
  document.getElementById("wBtnBack").style.display = wState.step > 1 ? "" : "none";
  document.getElementById("wBtnNext").textContent    = wState.step === 3 ? "Deploy" : "Next →";

  if (wState.step === 1) wRenderSubnets();
  if (wState.step === 2) { wRenderVms(); wPopulateVmForm(); }
  if (wState.step === 3) wRenderReview();
}

/* ── Step 1: Subnets ─────────────────────────────────────────────────────── */

function wAddSubnet(preset) {
  if (wState.subnets.length >= 5) { alert("Maximum 5 subnets."); return; }
  const p = SUBNET_PRESETS[preset];
  if (!p) return;
  if (wState.subnets.find(s => s.name === p.name)) {
    alert(`${p.name} already added.`); return;
  }
  wState.subnets.push({name: p.name, preset: p.name, base: p.base, color: p.color});
  wRenderSubnets();
}

function wRemoveSubnet(idx) {
  const removed = wState.subnets[idx].name;
  wState.subnets.splice(idx, 1);
  // Remove subnet refs from VMs
  wState.vms = wState.vms.map(vm => ({
    ...vm, subnets: vm.subnets.filter(s => s !== removed)
  })).filter(vm => vm.subnets.length > 0 || vm.role === "endpoint");
  wRenderSubnets();
}

function wRenderSubnets() {
  const el = document.getElementById("wSubnetList");
  if (!wState.subnets.length) {
    el.innerHTML = `<div class="wizard-empty">No subnets yet — click a preset above to add one.</div>`;
    return;
  }
  el.innerHTML = wState.subnets.map((s, i) => `
    <div class="wizard-item">
      <div class="topo-subnet-box ${s.color} wizard-subnet-box">
        <div class="topo-subnet-name">${s.name}</div>
        <div class="topo-subnet-net">${s.base}.0/24</div>
      </div>
      <div class="wizard-item-info" style="flex:1">
        <div style="display:flex;align-items:center;gap:6px;font-size:12px">
          <span style="color:var(--muted)">Base IP:</span>
          <input type="text" value="${s.base}" maxlength="15"
            style="width:120px;padding:2px 6px;font-size:12px;background:var(--surface);border:1px solid var(--border);border-radius:4px;color:var(--text)"
            oninput="wUpdateSubnetBase(${i}, this.value)"
            placeholder="e.g. 10.0.1" />
          <span style="color:var(--muted)">.0/24</span>
        </div>
        <div style="color:var(--muted);font-size:11px;margin-top:2px">
          DHCP: ${s.base}.100–${s.base}.200 &nbsp;·&nbsp; Gateway: ${s.base}.1
        </div>
      </div>
      <button class="btn btn-danger" style="padding:3px 8px;font-size:11px;flex-shrink:0" onclick="wRemoveSubnet(${i})">✕</button>
    </div>`).join("");
}

function wUpdateSubnetBase(idx, val) {
  // Accept dotted-decimal base (e.g. "10.0.1" or "192.168.30")
  const trimmed = val.trim().replace(/\.$/, "");
  wState.subnets[idx].base   = trimmed;
  wState.subnets[idx].preset = null;  // stop backend from using hardcoded preset config
  // Live-update the displayed DHCP/gateway hint without full re-render
  const items = document.querySelectorAll("#wSubnetList .wizard-item");
  if (items[idx]) {
    const hint = items[idx].querySelector(".wizard-item-info div:last-child");
    const net  = items[idx].querySelector(".topo-subnet-net");
    if (hint) hint.textContent = `DHCP: ${trimmed}.100–${trimmed}.200  ·  Gateway: ${trimmed}.1`;
    if (net)  net.textContent  = `${trimmed}.0/24`;
  }
}

/* ── Step 2: VMs ─────────────────────────────────────────────────────────── */

function wRenderVms() {
  const el = document.getElementById("wVmList");
  if (!wState.vms.length) {
    el.innerHTML = `<div class="wizard-empty">No VMs yet — click "+ Add VM" below.</div>`;
    return;
  }
  el.innerHTML = wState.vms.map((vm, i) => {
    const roleCls = vm.role === "firewall" ? "role-firewall" : "";
    return `
    <div class="wizard-item">
      <div>
        <div style="font-weight:600;font-size:13px">${vm.name}</div>
        <div style="font-size:11px;color:var(--muted)">${vm.image_filename}</div>
      </div>
      <div class="wizard-item-info">
        <span class="role-badge ${roleCls}">${vm.role}</span>
        <span style="font-size:11px;color:var(--muted)">${vm.subnets.join(" → ")}</span>
      </div>
      <button class="btn btn-danger" style="padding:3px 8px;font-size:11px" onclick="wRemoveVm(${i})">✕</button>
    </div>`;
  }).join("");
}

function wRemoveVm(idx) {
  wState.vms.splice(idx, 1);
  wRenderVms();
}

function wShowAddVmForm() {
  document.getElementById("wAddVmForm").style.display = "";
  document.getElementById("wBtnAddVm").style.display  = "none";
  wPopulateVmForm();
}

function wHideAddVmForm() {
  document.getElementById("wAddVmForm").style.display = "none";
  document.getElementById("wBtnAddVm").style.display  = "";
}

function wPopulateVmForm() {
  wUpdateVmForm();
}

function wUpdateVmForm() {
  const role   = document.getElementById("wVmRole")?.value || "endpoint";
  const imgSel = document.getElementById("wVmImage");
  const subSel = document.getElementById("wEndpointSubnet");
  const wanSel = document.getElementById("wFwWan");
  const lanDiv = document.getElementById("wFwLanChecks");
  if (!imgSel) return;

  // Populate image dropdown (all images, not filtered by role)
  imgSel.innerHTML = wState.images.length
    ? wState.images.map(img =>
        `<option value="${img.filename}" data-type="${img.type}" data-ostype="${img.ostype}">
          ${img.filename} (${img.size_mb} MB)
        </option>`).join("")
    : `<option value="">No images found</option>`;

  // Show/hide endpoint vs firewall fields
  const isFirewall = role === "firewall";
  document.getElementById("wEndpointSubnetRow").style.display = isFirewall ? "none" : "";
  document.getElementById("wFirewallRows").style.display      = isFirewall ? ""     : "none";

  // Populate subnet pickers
  const subnetOpts = wState.subnets.map(s =>
    `<option value="${s.name}">${s.name} (${s.base}.0/24)</option>`).join("");

  if (subSel) subSel.innerHTML = subnetOpts;
  if (wanSel) wanSel.innerHTML = subnetOpts;

  if (lanDiv) {
    lanDiv.innerHTML = wState.subnets.map(s =>
      `<label class="wform-check">
        <input type="checkbox" name="fw_lan" value="${s.name}"> ${s.name}
      </label>`).join("");
  }
}

function wAddVm() {
  const name  = document.getElementById("wVmName").value.trim();
  const role  = document.getElementById("wVmRole").value;
  const imgEl = document.getElementById("wVmImage");
  const selOpt = imgEl?.selectedOptions[0];

  if (!name)   { alert("Enter a VM name."); return; }
  if (!selOpt) { alert("No images available."); return; }
  if (wState.vms.find(v => v.name === name)) { alert(`Name "${name}" already used.`); return; }

  const filename  = selOpt.value;
  const img_type  = selOpt.dataset.type  || "ova";
  const ostype    = selOpt.dataset.ostype || "Other_64";

  let vmSubnets = [];

  if (role === "firewall") {
    const wan  = document.getElementById("wFwWan").value;
    const lans = [...document.querySelectorAll('#wFwLanChecks input[name="fw_lan"]:checked')]
                   .map(cb => cb.value);
    if (!wan)          { alert("Select a WAN subnet."); return; }
    if (!lans.length)  { alert("Select at least one LAN subnet."); return; }
    if (lans.includes(wan)) { alert("WAN and LAN cannot be the same subnet."); return; }
    vmSubnets = [wan, ...lans];
  } else {
    const sub = document.getElementById("wEndpointSubnet").value;
    if (!sub) { alert("Select a subnet."); return; }
    vmSubnets = [sub];
  }

  wState.vms.push({name, role, image_filename: filename, image_type: img_type, ostype, subnets: vmSubnets});
  document.getElementById("wVmName").value = "";
  wHideAddVmForm();
  wRenderVms();
}

/* ── Step 3: Review ──────────────────────────────────────────────────────── */

function wRenderReview() {
  const el = document.getElementById("wReviewContent");
  const fwVms = wState.vms.filter(v => v.role === "firewall");
  const epVms = wState.vms.filter(v => v.role === "endpoint");

  // Connectivity analysis
  const connected = new Set();
  fwVms.forEach(fw => {
    const all = fw.subnets;
    for (let i = 0; i < all.length; i++)
      for (let j = i+1; j < all.length; j++)
        connected.add([all[i],all[j]].sort().join("|"));
  });

  const subnetNames = wState.subnets.map(s => s.name);
  let connectRows = "";
  for (let i = 0; i < subnetNames.length; i++) {
    for (let j = i+1; j < subnetNames.length; j++) {
      const key = [subnetNames[i],subnetNames[j]].sort().join("|");
      const ok  = connected.has(key);
      connectRows += `<div class="review-connect ${ok ? "ok" : "iso"}">
        ${ok ? "&#10003;" : "&#10007;"} ${subnetNames[i]} ↔ ${subnetNames[j]}
        <span>${ok ? "Connected via firewall" : "Isolated"}</span>
      </div>`;
    }
  }

  el.innerHTML = `
    <div class="review-section">
      <div class="review-label">Subnets (${wState.subnets.length})</div>
      ${wState.subnets.map(s => `<div class="review-row">
        <span class="topo-fw-label" style="border-color:transparent;background:transparent;color:var(--text)">${s.name}</span>
        <span style="color:var(--muted);font-size:11px">${s.base}.0/24 &nbsp;·&nbsp; DHCP ${s.base}.100–200</span>
      </div>`).join("")}
    </div>
    <div class="review-section">
      <div class="review-label">Virtual Machines (${wState.vms.length})</div>
      ${wState.vms.map(vm => `<div class="review-row">
        <span class="role-badge ${vm.role==="firewall"?"role-firewall":""}">${vm.role}</span>
        <span style="font-weight:600">${vm.name}</span>
        <span style="color:var(--muted);font-size:11px">${vm.subnets.join(" → ")}</span>
      </div>`).join("")}
    </div>
    ${subnetNames.length >= 2 ? `
    <div class="review-section">
      <div class="review-label">Connectivity</div>
      ${connectRows}
    </div>` : ""}`;
}

/* ── Deploy custom lab ───────────────────────────────────────────────────── */

async function wDeploy() {
  const name = document.getElementById("wLabName").value.trim() || "Custom Lab";

  // Validate subnet base IPs before deploying
  const baseRe = /^\d{1,3}\.\d{1,3}\.\d{1,3}$/;
  for (const s of wState.subnets) {
    if (!baseRe.test(s.base)) {
      alert(`Invalid IP for subnet "${s.name}": "${s.base}"\nEnter three octets, e.g. 192.168.10`);
      return;
    }
  }

  closeCustomWizard();
  logOffset = 0;
  document.getElementById("logOutput").innerHTML = "";

  const res = await fetch("/api/custom-deploy", {
    method:  "POST",
    headers: {"Content-Type": "application/json"},
    body:    JSON.stringify({
      name,
      subnets: wState.subnets.map(s => ({name: s.name, preset: s.preset, base: s.base})),
      vms:     wState.vms,
    }),
  });
  const data = await res.json();
  if (!res.ok) appendLog("ERROR: " + (data.error || "Deploy failed"), "log-err");
}
