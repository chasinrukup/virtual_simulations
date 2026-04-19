#!/usr/bin/env python3
"""
End-to-end test for all 3 prebuilt scenarios.
For each scenario: deploy, test connectivity, test SSH, then tear down.
"""

import os
import sys
import time
import socket
import subprocess

import vbox
import prebuilt
import deployer
import vm_manager
import network_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Helpers ──────────────────────────────────────────────────────────────────

def check_port(ip, port, timeout=3):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def get_vm_mac(vm_name, nic=1):
    info = vbox.run(["showvminfo", vm_name, "--machinereadable"], check=False)
    if not info:
        return None
    key = f"macaddress{nic}"
    for line in info.splitlines():
        if line.lower().startswith(key + "="):
            raw = line.split("=", 1)[1].strip('"')
            mac = "-".join(raw[i:i+2] for i in range(0, len(raw), 2)).lower()
            return mac
    return None


def get_arp_table():
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
        mac_to_ip = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1].count("-") == 5:
                mac_to_ip[parts[1].lower()] = parts[0]
        return mac_to_ip
    except Exception:
        return {}


def discover_ips(config, max_attempts=5, wait_secs=15):
    """Discover IPs for all running VMs with retries."""
    running_vms = []
    for vm in config.vms:
        state = vm_manager.get_vm_state(vm.name)
        if state != "running":
            continue
        mac = get_vm_mac(vm.name, 1)
        running_vms.append((vm.name, mac))

    if not running_vms:
        return {}

    vm_ips = {}

    for attempt in range(1, max_attempts + 1):
        missing = [(n, m) for n, m in running_vms if n not in vm_ips and m]
        if not missing:
            break

        if attempt > 1:
            print(f"    Retry {attempt}/{max_attempts} — waiting {wait_secs}s for DHCP...")
            time.sleep(wait_secs)

        # Ping sweep all subnets
        for subnet in config.subnets:
            if not (subnet.dhcp and subnet.dhcp.enabled):
                continue
            base = subnet.network.rsplit(".", 1)[0]
            lower = int(subnet.dhcp.lower_ip.rsplit(".", 1)[1])
            upper = int(subnet.dhcp.upper_ip.rsplit(".", 1)[1])
            for i in range(lower, upper + 1):
                ip = f"{base}.{i}"
                subprocess.run(["ping", "-n", "1", "-w", "300", ip],
                               capture_output=True, creationflags=0x08000000)

        arp = get_arp_table()
        for name, mac in missing:
            if mac in arp:
                vm_ips[name] = arp[mac]

    return vm_ips


def ping_host_to_vm(ip):
    result = subprocess.run(["ping", "-n", "3", "-w", "1000", ip],
                            capture_output=True, text=True, creationflags=0x08000000)
    return result.returncode == 0


def test_ssh_connect(ip, port=22, timeout=5):
    """Test if SSH banner is returned (confirms sshd is running)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        banner = sock.recv(256)
        sock.close()
        return banner.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return None


def teardown_scenario(config):
    """Stop and delete all VMs from a scenario."""
    for vm in config.vms:
        state = vm_manager.get_vm_state(vm.name)
        if state == "running":
            vm_manager.stop_vm(vm.name, force=True)
    time.sleep(3)
    for vm in config.vms:
        if vm_manager.vm_exists(vm.name):
            # For .vbox VMs, only unregister (preserve source files)
            keep = getattr(vm, "image_type", "ova") == "vbox"
            vm_manager.delete_vm(vm.name, keep_files=keep)


# ── Main Test ────────────────────────────────────────────────────────────────

def test_scenario(scenario_idx):
    scenario = prebuilt.SCENARIOS[scenario_idx]
    name = scenario["name"]

    print()
    print("=" * 70)
    print(f"  SCENARIO {scenario_idx + 1}: {name}")
    print("=" * 70)

    # Check readiness
    ok, missing = prebuilt.check_scenario(scenario)
    if not ok:
        print(f"  SKIP — missing images: {missing}")
        return False

    # Build config
    config = prebuilt.build_scenario_config(scenario)
    if not config:
        print("  FAIL — could not build config")
        return False

    fw_count = len(config.firewalls)
    print(f"  Subnets: {[s.name for s in config.subnets]}")
    print(f"  VMs: {[vm.name for vm in config.vms]}")
    print(f"  Firewalls: {[fw.vm_name for fw in config.firewalls] if config.firewalls else 'None'}")

    # Deploy
    print(f"\n  --- Deploying ---")
    success = deployer.deploy_lab(config, headless=True)
    if not success:
        print("  FAIL — deployment failed")
        teardown_scenario(config)
        return False

    # Wait for VMs to boot (longer if firewall present — pfSense is slow)
    wait = 45 if config.firewalls else 30
    print(f"\n  --- Waiting {wait}s for VMs to boot ---")
    time.sleep(wait)

    # Discover IPs
    print(f"\n  --- Discovering IPs ---")
    vm_ips = discover_ips(config)

    for vm in config.vms:
        ip = vm_ips.get(vm.name, "NOT FOUND")
        print(f"    {vm.name:25s} -> {ip}")

    # Check pfSense LAN IPs for all firewalls
    fw_lan_ips = {}  # fw.vm_name -> LAN ip
    subnet_map = {s.name: s for s in config.subnets}
    for fw in config.firewalls:
        fw_lan_ip = None
        for attempt in range(3):
            for lan_name in fw.lan_subnets:
                subnet = subnet_map.get(lan_name)
                if subnet:
                    base = subnet.network.rsplit(".", 1)[0]
                    candidate = f"{base}.254"
                    if check_port(candidate, 443, timeout=3) or check_port(candidate, 22, timeout=3):
                        fw_lan_ip = candidate
                        break
            if fw_lan_ip:
                break
            if attempt < 2:
                print(f"    {fw.vm_name} LAN not ready, waiting 15s...")
                time.sleep(15)
        if fw_lan_ip:
            fw_lan_ips[fw.vm_name] = fw_lan_ip
            print(f"    {(fw.vm_name + ' (LAN)'):25s} -> {fw_lan_ip}")
        else:
            print(f"    {fw.vm_name} LAN IP not detected (192.168.x.254 not responding)")

    # Use first firewall's LAN IP for SSH test compat
    fw_lan_ip = next(iter(fw_lan_ips.values()), None)

    # Test 1: Host -> VM ping
    print(f"\n  --- Test: Host -> VM Ping ---")
    ping_results = {}
    for vm in config.vms:
        ip = vm_ips.get(vm.name)
        if ip:
            ok = ping_host_to_vm(ip)
            status = "OK" if ok else "BLOCKED"
            if vm.role == "firewall" and not ok:
                status = "BLOCKED (normal for firewall WAN)"
            ping_results[vm.name] = ok
            print(f"    Ping {vm.name:25s} ({ip:15s}): {status}")
        else:
            ping_results[vm.name] = False
            print(f"    Ping {vm.name:25s}: SKIP (no IP)")

    # Test pfSense LAN ping
    if fw_lan_ip:
        ok = ping_host_to_vm(fw_lan_ip)
        print(f"    Ping {'pfSense LAN':25s} ({fw_lan_ip:15s}): {'OK' if ok else 'BLOCKED'}")

    # Test 2: Port scanning
    print(f"\n  --- Test: Port Scan ---")
    port_results = {}
    for vm in config.vms:
        ip = vm_ips.get(vm.name)
        if not ip:
            continue
        ports_open = []
        for port, svc in [(22, "SSH"), (80, "HTTP"), (443, "HTTPS"), (21, "FTP")]:
            if check_port(ip, port, timeout=2):
                ports_open.append(f"{port}/{svc}")
        port_results[vm.name] = ports_open
        print(f"    {vm.name:25s} ({ip:15s}): {', '.join(ports_open) if ports_open else 'no open ports'}")

    # Scan all pfSense LAN IPs
    for fw_name, lan_ip in fw_lan_ips.items():
        ports_open = []
        for port, svc in [(22, "SSH"), (80, "HTTP"), (443, "HTTPS")]:
            if check_port(lan_ip, port, timeout=2):
                ports_open.append(f"{port}/{svc}")
        port_results[f"{fw_name}_LAN"] = ports_open
        print(f"    {(fw_name + ' LAN'):25s} ({lan_ip:15s}): {', '.join(ports_open) if ports_open else 'no open ports'}")

    # Test 3: SSH banner check
    print(f"\n  --- Test: SSH Access ---")
    ssh_results = {}
    for vm in config.vms:
        ip = vm_ips.get(vm.name)
        if vm.role == "firewall":
            # Use LAN IP for firewall
            test_ip = fw_lan_ip or ip
            label = f"{vm.name} (LAN: {test_ip})" if fw_lan_ip else vm.name
        else:
            test_ip = ip
            label = vm.name

        if not test_ip:
            ssh_results[vm.name] = False
            print(f"    {label:40s}: SKIP (no IP)")
            continue

        banner = test_ssh_connect(test_ip)
        if banner:
            ssh_results[vm.name] = True
            print(f"    {label:40s}: OK — {banner}")
        else:
            ssh_results[vm.name] = False
            print(f"    {label:40s}: FAILED (no SSH response)")

    # Summary
    print(f"\n  --- Summary ---")
    total_vms = len(config.vms)
    ips_found = sum(1 for vm in config.vms if vm.name in vm_ips)
    ssh_ok = sum(1 for v in ssh_results.values() if v)
    print(f"    IPs discovered: {ips_found}/{total_vms}")
    print(f"    SSH accessible:  {ssh_ok}/{total_vms}")

    all_pass = ips_found == total_vms and ssh_ok == total_vms
    if not all_pass:
        # Check if partial pass is expected (some VMs don't have SSH)
        no_ssh = [vm.name for vm in config.vms if not ssh_results.get(vm.name)]
        if no_ssh:
            print(f"    No SSH on: {', '.join(no_ssh)}")

    print(f"\n    RESULT: {'PASS' if all_pass else 'PARTIAL'}")

    # Teardown
    print(f"\n  --- Tearing down ---")
    teardown_scenario(config)
    time.sleep(5)

    return all_pass


def main():
    vbox.check_vbox()

    print()
    print("=" * 70)
    print("  PREBUILT SCENARIO END-TO-END TEST")
    print("=" * 70)
    print(f"  Testing all {len(prebuilt.SCENARIOS)} scenarios sequentially.")
    print(f"  Each scenario: deploy -> connectivity -> SSH -> teardown")

    results = {}
    for i in range(len(prebuilt.SCENARIOS)):
        results[i] = test_scenario(i)

    # Final report
    print()
    print("=" * 70)
    print("  FINAL RESULTS")
    print("=" * 70)
    for i, passed in results.items():
        name = prebuilt.SCENARIOS[i]["name"]
        status = "PASS" if passed else "PARTIAL/FAIL"
        print(f"    Scenario {i+1}: {name:35s} [{status}]")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
    except Exception as e:
        import traceback
        traceback.print_exc()
