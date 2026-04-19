"""
Flask web server for the Virtual Network Simulation Lab.
Exposes the CLI backend (deployer, vm_manager, prebuilt) over HTTP
so any browser on the network can control the lab.
"""

import os
import sys
import threading
import time

from flask import Flask, render_template, jsonify, request

# ── Point modules at the images directory before importing them ───────────────

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import web_config

import prebuilt
import deployer
import vm_manager
import config_store
import validator
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
_handler.setFormatter(logging.Formatter("%(message)s"))
get_logger().addHandler(_handler)

def _append_log(msg):
    with _log_lock:
        _log_lines.append(msg)

# ── In-memory lab state ───────────────────────────────────────────────────────

_state = {
    "status":        "idle",   # idle | deploying | running | stopping
    "scenario_name": None,
    "config":        None,     # active LabConfig
}
_state_lock = threading.Lock()

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

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
    data = request.json or {}
    scenario_id = data.get("scenario_id")

    with _state_lock:
        if _state["status"] == "deploying":
            return jsonify({"error": "Deployment already in progress"}), 409
        _state["status"]        = "deploying"
        _state["scenario_name"] = None
        _state["config"]        = None

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

        success = deployer.deploy_lab(config, headless=True)

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
            vms.append({
                "name":    vm.name,
                "role":    vm.role,
                "subnets": vm.subnets,
                "state":   vm_manager.get_vm_state(vm.name),
            })

    return jsonify({
        "status":    status,
        "scenario":  scenario,
        "vms":       vms,
        "firewalls": [
            {"vm_name": fw.vm_name,
             "wan":     fw.wan_subnet,
             "lan":     fw.lan_subnets}
            for fw in (config.firewalls if config else [])
        ],
        "subnets": [
            {"name":    s.name,
             "network": s.network,
             "gateway": s.gateway_ip}
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
        _append_log("Lab deleted. Ready for next deployment.")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n  Virtual Network Simulation Lab")
    print(f"  Open in browser: http://localhost:{web_config.PORT}\n")
    app.run(host=web_config.HOST, port=web_config.PORT, debug=False, threaded=True)
