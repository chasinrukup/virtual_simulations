/* ── State ──────────────────────────────────────────────────────────────── */
let scenarios       = [];
let selectedScenario = null;
let logOffset       = 0;
let pollTimer       = null;

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
  closeModal();
  logOffset = 0;
  document.getElementById("logOutput").innerHTML = "";

  const res = await fetch("/api/deploy", {
    method:  "POST",
    headers: {"Content-Type": "application/json"},
    body:    JSON.stringify({scenario_id: selectedScenario}),
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
async function pollLog() {
  try {
    const res  = await fetch(`/api/log?since=${logOffset}`);
    const data = await res.json();
    updateStatusIndicator(data.status, data.scenario);

    data.lines.forEach(line => {
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

/* ── Status polling ──────────────────────────────────────────────────────── */
async function pollStatus() {
  try {
    const res  = await fetch("/api/status");
    const data = await res.json();
    renderTopology(data);
    renderVmTable(data);
    updateControls(data);
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

  // Build subnet -> VMs map
  const subnetVMs = {};
  const fwNames   = new Set((data.firewalls || []).map(f => f.vm_name));
  data.subnets.forEach(s => { subnetVMs[s.name] = []; });
  (data.vms || []).forEach(vm => {
    if (fwNames.has(vm.name)) return;
    vm.subnets.forEach(sn => {
      if (subnetVMs[sn]) subnetVMs[sn].push(vm);
    });
  });

  // Build ordered list: subnets interleaved with firewalls that bridge them
  const rendered = [];
  const subnets  = data.subnets;

  subnets.forEach((subnet, idx) => {
    // Add connector (firewall) between subnets if one bridges them
    if (idx > 0) {
      const prevSubnet = subnets[idx - 1];
      const bridgeFW   = (data.firewalls || []).find(fw => {
        const all = [fw.wan, ...fw.lan];
        return all.includes(prevSubnet.name) && all.includes(subnet.name);
      });
      rendered.push({type: "connector", fw: bridgeFW || null});
    }
    rendered.push({type: "subnet", subnet, vms: subnetVMs[subnet.name] || []});
  });

  el.className = "";
  const diag = document.createElement("div");
  diag.className = "topology-diagram";

  rendered.forEach(item => {
    if (item.type === "connector") {
      const conn = document.createElement("div");
      conn.className = "topo-connector";
      if (item.fw) {
        conn.innerHTML = `
          <div class="topo-line"></div>
          <div class="topo-fw-box">
            <div class="topo-fw-label">&#9650; ${item.fw.vm_name}</div>
            <div style="font-size:9px;color:var(--muted);text-align:center">
              ${item.fw.wan} ↔ ${item.fw.lan.join(",")}
            </div>
          </div>
          <div class="topo-line"></div>`;
      } else {
        conn.innerHTML = `<div class="topo-line" style="width:50px"></div>`;
      }
      diag.appendChild(conn);
    } else {
      const s    = item.subnet;
      const cls  = subnetColorClass(s.name);
      const node = document.createElement("div");
      node.className = "topo-subnet";

      const vmsHtml = item.vms.map(vm => {
        const col = stateColor(vm.state);
        return `<div class="topo-vm">
          <div class="topo-vm-dot" style="background:${col}"></div>
          <span style="font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:90px"
                title="${vm.name}">${vm.name}</span>
        </div>`;
      }).join("");

      node.innerHTML = `
        <div class="topo-subnet-box ${cls}">
          <div class="topo-subnet-name">${s.name}</div>
          <div class="topo-subnet-net">${s.network}</div>
        </div>
        <div class="topo-vms">${vmsHtml}</div>`;
      diag.appendChild(node);
    }
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

  const rows = data.vms.map(vm => {
    const isfw   = fwNames.has(vm.name);
    const stCls  = vm.state === "running"  ? "state-running"
                 : vm.state === "poweroff" ? "state-poweroff" : "state-other";
    const rolCls = isfw ? "role-badge role-firewall" : "role-badge";
    const roleLabel = isfw ? "firewall" : vm.role;
    const subnets = vm.subnets.join(", ");

    return `<tr>
      <td>${vm.name}</td>
      <td><span class="${rolCls}">${roleLabel}</span></td>
      <td>${subnets}</td>
      <td><span class="state-badge ${stCls}">
        &#9679; ${vm.state}
      </span></td>
    </tr>`;
  }).join("");

  el.innerHTML = `
    <table class="vm-table">
      <thead><tr>
        <th>Name</th><th>Role</th><th>Subnets</th><th>State</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ── Control buttons ─────────────────────────────────────────────────────── */
function updateControls(data) {
  const hasLab    = data.vms && data.vms.length > 0;
  const isRunning = data.status === "running" || data.status === "stopped";
  const isBusy    = data.status === "deploying" || data.status === "stopping";

  document.getElementById("btnStop").disabled   = !hasLab || isBusy;
  document.getElementById("btnDelete").disabled = !hasLab || isBusy;
}

async function stopAll() {
  if (!confirm("Stop all running VMs?")) return;
  await fetch("/api/stop", {method: "POST"});
}

async function teardown() {
  if (!confirm("Stop and DELETE all VMs in this lab?")) return;
  await fetch("/api/teardown", {method: "POST"});
}
