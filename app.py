"""
Flask web server for the Virtual Network Simulation Lab.
Exposes the CLI backend (deployer, vm_manager, prebuilt) over HTTP
so any browser on the network can control the lab.
"""

import os
import sys
import threading
import time

import re
import subprocess
from flask import Flask, render_template, jsonify, request

# ── Point modules at the images directory before importing them ───────────────

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import web_config

import prebuilt
import deployer
import vm_manager
import config_store
import validator
import vbox
from logger import get_logger

# Redirect image search to the CLI folder where OVAs actually live
prebuilt.BASE_DIR   = web_config.IMAGES_DIR
config_store.BASE_DIR = web_config.IMAGES_DIR

# ── Capture log output for the UI ─────────────────────────────────────────────

import logging

_log_lines = []
_log_lock  = threading.Lock()

class _WebLogHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        with _log_lock:
            _log_lines.append(msg)
            if len(_log_lines) > 500:   # cap memory usage
                _log_lines.pop(0)

_handler = _WebLogHandler()
_handler.setLevel(logging.INFO)          # filter out DEBUG (VBoxManage commands/stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))
get_logger().addHandler(_handler)

def _append_log(msg):
    with _log_lock:
        _log_lines.append(msg)

# ── SSH credential hints (by source image name) ───────────────────────────────
# These are the default credentials baked into each VM image.
# Update here if your images use different credentials.
_VM_CREDS = {
    "emyers_unbuntu_vsftpd.ova":              {"user": "john",  "pass": "admin"},
    "emyers-vulnhu-php":                      {"user": "john",  "pass": "admin"},
    "pfSense_export.ova":                     {"user": "john",  "pass": "admin",
                                               "note": "web UI at https://gateway-ip"},
    "kali-linux-2025.4-virtualbox-amd64":     {"user": "kali",  "pass": "kali"},
}

def _get_creds(vm_iso_path):
    """Return credential hints for a VM by matching its source path/name."""
    for key, creds in _VM_CREDS.items():
        if key in (vm_iso_path or ""):
            return creds
    return {}

# ── In-memory lab state ───────────────────────────────────────────────────────

_state = {
    "status":        "idle",   # idle | deploying | running | stopping
    "scenario_name": None,
    "config":        None,     # active LabConfig
    "is_prebuilt":   False,    # True when deployed via /api/deploy (pre-built scenario)
}
_state_lock = threading.Lock()

# ── VNC desktop proxy processes (one per Kali VM) ─────────────────────────────
_vnc_proxies     = {}   # {vm_name: subprocess.Popen}
_vnc_proxy_lock  = threading.Lock()

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

# WebSocket support (requires: pip install flask-sock paramiko)
try:
    from flask_sock import Sock as _Sock
    sock = _Sock(app)
    _SOCK_OK = True
except ImportError:
    _SOCK_OK = False

# ── Health check ─────────────────────────────────────────────────────────────

@app.route("/api/ping")
def api_ping():
    return jsonify({"ok": True, "scenarios": len(prebuilt.SCENARIOS)})

# ── Page ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

# ── Scenarios ─────────────────────────────────────────────────────────────────

@app.route("/api/scenarios")
def api_scenarios():
    result = []
    for i, s in enumerate(prebuilt.SCENARIOS):
        ok, missing = prebuilt.check_scenario(s)
        result.append({
            "id":              i,
            "name":            s["name"],
            "description":     s["description"],
            "layout":          s["layout"],
            "subnets":         s["subnets"],
            "vm_count":        len(s["vms"]),
            "firewall_count":  len(s.get("firewalls", [])),
            "available":       ok,
            "missing":         missing,
        })
    return jsonify(result)

# ── Deploy ────────────────────────────────────────────────────────────────────

@app.route("/api/deploy", methods=["POST"])
def api_deploy():
    data = request.get_json(force=True, silent=True) or {}
    scenario_id = data.get("scenario_id")
    # Coerce string to int in case the browser sends "0" instead of 0
    if scenario_id is not None:
        try:
            scenario_id = int(scenario_id)
        except (ValueError, TypeError):
            scenario_id = None

    with _state_lock:
        if _state["status"] == "deploying":
            return jsonify({"error": "Deployment already in progress"}), 409
        _state["status"]        = "deploying"
        _state["scenario_name"] = None
        _state["config"]        = None
        _state["is_prebuilt"]   = True

    with _log_lock:
        _log_lines.clear()

    if scenario_id is None or not (0 <= scenario_id < len(prebuilt.SCENARIOS)):
        with _state_lock:
            _state["status"] = "idle"
        return jsonify({"error": "Invalid scenario ID"}), 400

    scenario = prebuilt.SCENARIOS[scenario_id]

    def _run():
        _append_log(f"=== Deploying: {scenario['name']} ===")
        config = prebuilt.build_scenario_config(scenario)
        if not config:
            _append_log("ERROR: Could not build config — check image availability.")
            with _state_lock:
                _state["status"] = "idle"
            return

        with _state_lock:
            _state["scenario_name"] = scenario["name"]
            _state["config"]        = config

        success = deployer.deploy_lab(config, headless=False)

        with _state_lock:
            _state["status"] = "running" if success else "idle"

        if not success:
            _append_log("=== DEPLOYMENT FAILED ===")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "scenario": scenario["name"]})

# ── Log stream (polled by UI) ─────────────────────────────────────────────────

@app.route("/api/log")
def api_log():
    since = int(request.args.get("since", 0))
    with _log_lock:
        lines = _log_lines[since:]
        total = len(_log_lines)
    with _state_lock:
        status   = _state["status"]
        scenario = _state["scenario_name"]
    return jsonify({"status": status, "scenario": scenario,
                    "lines": lines, "total": total})

# ── VM status (polled by UI) ──────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    with _state_lock:
        config   = _state["config"]
        status   = _state["status"]
        scenario = _state["scenario_name"]

    vms = []
    if config:
        for vm in config.vms:
            creds = _get_creds(vm.iso_path)
            vms.append({
                "name":     vm.name,
                "role":     vm.role,
                "subnets":  vm.subnets,
                "state":    vm_manager.get_vm_state(vm.name),
                "ssh_user": creds.get("user", ""),
                "ssh_pass": creds.get("pass", ""),
                "ssh_note": creds.get("note", ""),
                "is_kali":  "kali" in (vm.iso_path or "").lower(),
            })

    with _state_lock:
        is_prebuilt = _state.get("is_prebuilt", False)

    return jsonify({
        "status":      status,
        "scenario":    scenario,
        "is_prebuilt": is_prebuilt,
        "vms":         vms,
        "firewalls": [
            {"vm_name": fw.vm_name,
             "wan":     fw.wan_subnet,
             "lan":     fw.lan_subnets}
            for fw in (config.firewalls if config else [])
        ],
        "subnets": [
            {"name":       s.name,
             "network":    s.network,
             "gateway":    s.gateway_ip,
             "dhcp_start": s.dhcp.lower_ip if s.dhcp else "",
             "dhcp_end":   s.dhcp.upper_ip if s.dhcp else ""}
            for s in (config.subnets if config else [])
        ],
    })

# ── Stop / Teardown ───────────────────────────────────────────────────────────

@app.route("/api/stop", methods=["POST"])
def api_stop():
    with _state_lock:
        config = _state["config"]
        _state["status"] = "stopping"

    def _run():
        _append_log("Stopping all VMs...")
        deployer.stop_all(config, force=True)
        with _state_lock:
            _state["status"] = "stopped"
        _append_log("All VMs stopped.")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/teardown", methods=["POST"])
def api_teardown():
    with _state_lock:
        config = _state["config"]
        _state["status"] = "stopping"

    def _run():
        _append_log("Tearing down lab...")
        if config:
            deployer.stop_all(config, force=True)
            time.sleep(2)
            deployer.delete_all(config)
        with _state_lock:
            _state["status"]        = "idle"
            _state["config"]        = None
            _state["scenario_name"] = None
            _state["is_prebuilt"]   = False
        _append_log("Lab deleted. Ready for next deployment.")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})

# ── Background ping test ──────────────────────────────────────────────────

@app.route("/api/ping-test", methods=["POST"])
def api_ping_test():
    """SSH into each reachable endpoint VM and ping all others. Logs results."""
    import paramiko

    with _state_lock:
        config = _state["config"]
        status = _state["status"]

    if not config or status != "running":
        return jsonify({"error": "No running lab"}), 400

    def _run():
        fw_names  = {fw.vm_name for fw in config.firewalls}
        endpoints = [vm for vm in config.vms if vm.name not in fw_names]

        _append_log("")
        _append_log("=== Background Connectivity Ping Test ===")

        # Discover IPs for all endpoint VMs
        vm_ips = {}
        for vm in endpoints:
            ip = _get_vm_ip(vm.name)
            if ip:
                vm_ips[vm.name] = ip
                _append_log(f"  {vm.name}: {ip}")
            else:
                _append_log(f"  {vm.name}: IP not found — VM may still be booting")

        if len(vm_ips) < 2:
            _append_log("  Need at least 2 reachable VMs. Retry after VMs finish booting.")
            _append_log("=== Ping Test Skipped ===")
            return

        _append_log("")

        # SSH into each non-Kali reachable VM and ping all others
        for vm in endpoints:
            src_ip = vm_ips.get(vm.name)
            if not src_ip:
                continue
            is_kali = "kali" in (vm.iso_path or "").lower()
            if is_kali:
                _append_log(f"  {vm.name}: skipped (Kali SSH disabled by default)")
                continue

            creds = _get_creds(vm.iso_path)
            user  = creds.get("user", "john")
            pwd   = creds.get("pass", "admin")

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(src_ip, username=user, password=pwd, timeout=10,
                            look_for_keys=False, allow_agent=False)

                for tvm in endpoints:
                    if tvm.name == vm.name:
                        continue
                    tip = vm_ips.get(tvm.name)
                    if not tip:
                        _append_log(f"  {vm.name} → {tvm.name}: skipped (no IP)")
                        continue
                    _, out, _ = ssh.exec_command(f"ping -c 3 -W 2 {tip}")
                    result = out.read().decode()
                    reachable = "0% packet loss" in result
                    tag = "[OK] REACHABLE" if reachable else "[FAIL] UNREACHABLE"
                    _append_log(f"  {vm.name} ({src_ip}) → {tvm.name} ({tip}): {tag}")

                ssh.close()
            except paramiko.AuthenticationException:
                _append_log(f"  {vm.name}: SSH auth failed (user={user})")
            except Exception as e:
                _append_log(f"  {vm.name}: SSH error — {e}")

        _append_log("=== Ping Test Complete ===")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


# ── Available images (for custom mode) ───────────────────────────────────────

@app.route("/api/images")
def api_images():
    images = config_store.scan_images(web_config.IMAGES_DIR)
    return jsonify([{
        "filename":  img.filename,
        "size_mb":   img.size_mb,
        "ostype":    img.ostype,
        "type":      img.image_type,
        "role":      img.role or "endpoint",
    } for img in images])


# ── Custom lab deploy ─────────────────────────────────────────────────────────

@app.route("/api/custom-deploy", methods=["POST"])
def api_custom_deploy():
    data = request.get_json(force=True, silent=True) or {}

    with _state_lock:
        if _state["status"] == "deploying":
            return jsonify({"error": "Deployment already in progress"}), 409
        _state["status"]        = "deploying"
        _state["scenario_name"] = None
        _state["config"]        = None
        _state["is_prebuilt"]   = False

    with _log_lock:
        _log_lines.clear()

    subnet_defs = data.get("subnets", [])
    vm_defs     = data.get("vms",     [])
    lab_name    = data.get("name")  or "Custom Lab"

    if not subnet_defs or not vm_defs:
        with _state_lock:
            _state["status"] = "idle"
        return jsonify({"error": "Need at least one subnet and one VM"}), 400

    def _run():
        import copy
        from models import Subnet, DHCPConfig, VMConfig, FirewallConfig, LabConfig

        _append_log(f"=== Deploying: {lab_name} ===")

        # ── Build subnets ──────────────────────────────────────────────
        subnets = []
        for sd in subnet_defs:
            preset = sd.get("preset")
            if preset and preset in prebuilt._SUBNET_MAP:
                subnets.append(copy.deepcopy(prebuilt._SUBNET_MAP[preset]))
            else:
                base = sd.get("base", "192.168.99")
                subnets.append(Subnet(
                    name=sd["name"], network=f"{base}.0/24",
                    gateway_ip=f"{base}.1", netmask="255.255.255.0",
                    dhcp=DHCPConfig(
                        enabled=True, server_ip=f"{base}.2",
                        netmask="255.255.255.0",
                        lower_ip=f"{base}.100", upper_ip=f"{base}.200",
                    ),
                ))

        # ── Build VMs + auto-detect firewall configs ───────────────────
        vms       = []
        firewalls = []

        for vd in vm_defs:
            filename   = vd.get("image_filename", "")
            img_type   = vd.get("image_type",    "ova")
            role       = vd.get("role",          "endpoint")
            vm_subnets = vd.get("subnets",       [])
            ram_mb     = 1024 if role == "firewall" else 2048
            cpus       = 1    if role == "firewall" else 2

            if img_type == "clone":
                iso_path = filename
            else:
                iso_path = prebuilt._find_file(filename)
                if not iso_path:
                    _append_log(f"ERROR: Cannot find image '{filename}'")
                    with _state_lock:
                        _state["status"] = "idle"
                    return

            vms.append(VMConfig(
                name=vd["name"], ostype=vd.get("ostype", "Other_64"),
                ram_mb=ram_mb, cpus=cpus, disk_mb=0,
                iso_path=iso_path, image_type=img_type,
                role=role, subnets=vm_subnets,
            ))

            if role == "firewall" and len(vm_subnets) >= 2:
                firewalls.append(FirewallConfig(
                    vm_name=vd["name"],
                    wan_subnet=vm_subnets[0],
                    lan_subnets=vm_subnets[1:],
                ))

        config = LabConfig(subnets=subnets, vms=vms, firewalls=firewalls)

        with _state_lock:
            _state["scenario_name"] = lab_name
            _state["config"]        = config

        success = deployer.deploy_lab(config, headless=False)

        with _state_lock:
            _state["status"] = "running" if success else "idle"

        if not success:
            _append_log("=== DEPLOYMENT FAILED ===")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "name": lab_name})


# ── VM IP / SSH helpers ───────────────────────────────────────────────────────

def _get_vm_mac(vm_name):
    """Return NIC1 MAC address for a VM (formatted as AA-BB-CC-DD-EE-FF)."""
    info = vbox.run(["showvminfo", vm_name, "--machinereadable"], check=False) or ""
    for line in info.splitlines():
        if line.startswith("macaddress1="):
            raw = line.split("=")[1].strip('"').upper()
            if len(raw) == 12:
                return "-".join(raw[i:i+2] for i in range(0, 12, 2))
    return None



def _vm_creds_by_name(vm_name):
    """Return SSH credentials for a VM looked up from the active lab config."""
    with _state_lock:
        config = _state["config"]
    if not config:
        return {}
    for vm in config.vms:
        if vm.name == vm_name:
            return _get_creds(vm.iso_path)
    return {}


@app.route("/api/vm-ip/<vm_name>")
def api_vm_ip(vm_name):
    ip    = _get_vm_ip(vm_name)
    creds = _vm_creds_by_name(vm_name)
    hint  = ""
    with _state_lock:
        config = _state["config"]
    if config:
        for vm in config.vms:
            if vm.name == vm_name and vm.subnets:
                for s in config.subnets:
                    if s.name == vm.subnets[0] and s.dhcp:
                        hint = f"{s.dhcp.lower_ip} – {s.dhcp.upper_ip}"
                        break
    return jsonify({
        "ip":       ip,
        "hint":     hint,
        "ssh_user": creds.get("user", "john"),
        "ssh_pass": creds.get("pass", "admin"),
        "ssh_note": creds.get("note", ""),
    })


# ── SSH session management (polling-based, no WebSocket needed) ───────────────

import uuid as _uuid

_ssh_sessions     = {}   # {sid: {client, chan, buf, buf_lock}}
_ssh_sess_lock    = threading.Lock()


def _arp_lookup(mac):
    """Look up an IP in the host ARP table by MAC address (AA-BB-CC-DD-EE-FF)."""
    try:
        arp = subprocess.run(["arp", "-a"], capture_output=True, text=True).stdout
        for line in arp.splitlines():
            if mac.lower() in line.lower():
                parts = line.split()
                if parts and re.match(r'^\d+\.\d+\.\d+\.\d+$', parts[0]):
                    return parts[0]
    except Exception:
        pass
    return None


def _dhcp_lease_lookup(mac_dashes):
    """Check VirtualBox DHCP lease files for a MAC (AA-BB-CC-DD-EE-FF).
    Returns the leased IP string or None."""
    import glob as _glob, xml.etree.ElementTree as ET
    mac_colons = mac_dashes.lower().replace("-", ":")
    lease_dir  = os.path.join(os.path.expanduser("~"), ".VirtualBox")
    for path in _glob.glob(os.path.join(lease_dir, "*-Dhcpd.leases")):
        try:
            tree = ET.parse(path)
            for lease in tree.getroot().findall("Lease"):
                if lease.get("mac", "").lower() == mac_colons:
                    if lease.get("state") in ("acked", "offered"):
                        addr = lease.find("Address")
                        if addr is not None:
                            return addr.get("value")
        except Exception:
            pass
    return None


def _get_vm_ip(vm_name):
    """Find a VM's IP: ARP cache → DHCP leases → ping-sweep + ARP retry."""
    mac = _get_vm_mac(vm_name)
    if not mac:
        return None

    # 1. Fast path — already in ARP cache
    ip = _arp_lookup(mac)
    if ip:
        return ip

    # 2. Check VirtualBox DHCP lease files (works even without ARP traffic)
    ip = _dhcp_lease_lookup(mac)
    if ip:
        # Trigger a ping so the host's ARP cache learns the address
        subprocess.Popen(["ping", "-n", "1", "-w", "400", ip],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        return ip

    # 3. Slow path — ping-sweep the DHCP range, then retry ARP
    with _state_lock:
        config = _state["config"]
    if config:
        for vm in config.vms:
            if vm.name == vm_name and vm.subnets:
                for s in config.subnets:
                    if s.name == vm.subnets[0] and s.dhcp:
                        base = s.dhcp.lower_ip.rsplit(".", 1)[0]
                        pings = [
                            subprocess.Popen(
                                ["ping", "-n", "1", "-w", "400", f"{base}.{i}"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            for i in range(100, 121)
                        ]
                        for p in pings:
                            try: p.wait(timeout=0.7)
                            except Exception: pass
                        return _arp_lookup(mac)
    return None


@app.route("/api/ssh/start", methods=["POST"])
def api_ssh_start():
    import paramiko
    data = request.get_json(force=True, silent=True) or {}
    ip   = data.get("ip",   "")
    user = data.get("user", "john")
    pwd  = data.get("pass", "")
    cols = int(data.get("cols", 220))
    rows = int(data.get("rows",  50))

    if not ip:
        return jsonify({"error": "No IP provided"}), 400

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, password=pwd, timeout=10,
                       look_for_keys=False, allow_agent=False)
        chan = client.invoke_shell(term="xterm-256color", width=cols, height=rows)

        buf      = []
        buf_lock = threading.Lock()
        closed   = threading.Event()

        def _reader():
            try:
                while not closed.is_set():
                    if chan.recv_ready():
                        chunk = chan.recv(4096)
                        if not chunk:
                            break
                        with buf_lock:
                            buf.append(chunk.decode("utf-8", errors="replace"))
                    elif chan.closed or chan.exit_status_ready():
                        break
                    else:
                        time.sleep(0.01)
            except Exception:
                pass
            finally:
                closed.set()

        threading.Thread(target=_reader, daemon=True).start()

        sid = _uuid.uuid4().hex[:8]
        with _ssh_sess_lock:
            _ssh_sessions[sid] = {
                "client": client, "chan": chan,
                "buf": buf, "buf_lock": buf_lock, "closed": closed,
            }
        return jsonify({"ok": True, "sid": sid})

    except paramiko.AuthenticationException:
        return jsonify({"error": "Authentication failed — check username/password"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ssh/read/<sid>")
def api_ssh_read(sid):
    sess = _ssh_sessions.get(sid)
    if not sess:
        return jsonify({"data": "", "alive": False})
    with sess["buf_lock"]:
        out = "".join(sess["buf"])
        sess["buf"].clear()
    return jsonify({"data": out, "alive": not sess["closed"].is_set()})


@app.route("/api/ssh/write/<sid>", methods=["POST"])
def api_ssh_write(sid):
    sess = _ssh_sessions.get(sid)
    if not sess:
        return jsonify({"error": "No session"}), 404
    payload = request.get_data()
    try:
        sess["chan"].sendall(payload)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ssh/resize/<sid>", methods=["POST"])
def api_ssh_resize(sid):
    sess = _ssh_sessions.get(sid)
    if not sess:
        return jsonify({"error": "No session"}), 404
    d = request.get_json(force=True, silent=True) or {}
    try:
        sess["chan"].resize_pty(int(d.get("cols", 80)), int(d.get("rows", 24)))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ssh/close/<sid>", methods=["POST"])
def api_ssh_close(sid):
    with _ssh_sess_lock:
        sess = _ssh_sessions.pop(sid, None)
    if sess:
        sess["closed"].set()
        try: sess["chan"].close()
        except Exception: pass
        try: sess["client"].close()
        except Exception: pass
    return jsonify({"ok": True})

# ── Kali desktop (noVNC via x11vnc + websockify) ─────────────────────────────

@app.route("/api/vm-desktop/<vm_name>")
def api_vm_desktop(vm_name):
    """SSH into a Kali VM, start tightvncserver (XFCE desktop), then launch
    websockify on the host. Returns the WebSocket port for noVNC."""
    import paramiko

    ip = _get_vm_ip(vm_name)
    if not ip:
        return jsonify({"error": "VM IP not found — it may still be booting."}), 503

    creds = _vm_creds_by_name(vm_name)
    user  = creds.get("user", "john")
    pwd   = creds.get("pass", "admin")

    vnc_port = 5901   # tightvncserver display :1 → port 5901
    ws_port  = 6090   # WebSocket port on the host (noVNC connects here)

    # Kill any existing websockify proxy for this VM
    with _vnc_proxy_lock:
        old = _vnc_proxies.pop(vm_name, None)
    if old:
        try: old.terminate()
        except Exception: pass
    time.sleep(0.3)

    # SSH into Kali, set up tightvncserver with XFCE desktop
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=user, password=pwd, timeout=10,
                    look_for_keys=False, allow_agent=False)

        # Kill any stale VNC, set up password + xstartup, restart VNC
        _, out_setup, _ = ssh.exec_command(
            "mkdir -p ~/.vnc && "
            "printf 'kali' | vncpasswd -f > ~/.vnc/passwd && chmod 600 ~/.vnc/passwd && "
            "printf '#!/bin/bash\\nxrdb $HOME/.Xresources 2>/dev/null\\nstartxfce4\\n'"
            " > ~/.vnc/xstartup && chmod +x ~/.vnc/xstartup && "
            "tightvncserver -kill :1 2>/dev/null; "
            "tightvncserver :1 -geometry 1280x768 -depth 24 2>/dev/null; "
            "sleep 2; pgrep -f 'Xtightvnc.*:1' > /dev/null && echo ok || echo missing"
        )
        result = out_setup.read().decode().strip().splitlines()[-1]
        ssh.close()

        if result != "ok":
            return jsonify({"error":
                "tightvncserver failed to start in the VM.\n"
                "Try clicking Desktop again — it may need a moment."}), 503

    except paramiko.AuthenticationException:
        return jsonify({"error": "SSH authentication failed (user: kali / pass: kali)."}), 401
    except Exception as e:
        return jsonify({"error": f"Cannot SSH into VM: {e}"}), 503

    # Launch websockify on the host — bridges WebSocket to VNC TCP
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "websockify", str(ws_port), f"{ip}:{vnc_port}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with _vnc_proxy_lock:
            _vnc_proxies[vm_name] = proc
        time.sleep(0.5)
        if proc.poll() is not None:
            return jsonify({"error":
                "websockify failed to start.\n"
                "Install it: pip install websockify"}), 500
    except FileNotFoundError:
        return jsonify({"error":
            "websockify not found.\n"
            "Install it: pip install websockify"}), 500

    return jsonify({"ok": True, "ws_port": ws_port})


@app.route("/api/vm-desktop-stop", methods=["POST"])
def api_vm_desktop_stop():
    data    = request.get_json(force=True, silent=True) or {}
    vm_name = data.get("vm_name", "")
    with _vnc_proxy_lock:
        proc = _vnc_proxies.pop(vm_name, None)
    if proc:
        try: proc.terminate()
        except Exception: pass
    return jsonify({"ok": True})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n  Virtual Network Simulation Lab")
    print(f"  Open in browser: http://localhost:{web_config.PORT}\n")
    app.run(host=web_config.HOST, port=web_config.PORT, debug=False, threaded=True)
