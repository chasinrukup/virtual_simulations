#!/usr/bin/env python3
"""
Lab Builder for Existing VMs
─────────────────────────────
Uses VMs already registered in VirtualBox (OS installed, ready to run).
Does NOT create new VMs or mount ISOs.

Just: pick VMs → assign subnets → wire firewall → start.

Usage: python lab_existing.py
"""

import os
import sys

# VBoxManage path
VBOX = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"


# ── VBoxManage wrapper ──────────────────────────────────────────────────────

import subprocess

def vbox(args, check=True):
    """Run VBoxManage, return stdout or None on failure."""
    try:
        r = subprocess.run([VBOX] + args, capture_output=True, text=True, check=check)
        return r.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] {e.stderr.strip()}")
        return None


# ── Query VirtualBox ────────────────────────────────────────────────────────

def get_registered_vms():
    """Get all registered VMs with their state and config."""
    raw = vbox(["list", "vms"], check=False)
    if not raw:
        return []

    vms = []
    for line in raw.splitlines():
        if '"' not in line:
            continue
        name = line.split('"')[1]

        info = vbox(["showvminfo", name, "--machinereadable"], check=False) or ""
        props = {}
        for il in info.splitlines():
            if "=" in il:
                k, v = il.split("=", 1)
                props[k] = v.strip('"')

        vms.append({
            "name": name,
            "state": props.get("VMState", "unknown"),
            "ostype": props.get("ostype", "unknown"),
            "memory": props.get("memory", "?"),
            "cpus": props.get("cpus", "?"),
            "nic1": props.get("nic1", "none"),
            "nic2": props.get("nic2", "none"),
            "nic3": props.get("nic3", "none"),
            "nic4": props.get("nic4", "none"),
        })

    return vms


def get_hostonlyifs():
    """Get existing host-only adapters."""
    raw = vbox(["list", "hostonlyifs"], check=False)
    if not raw:
        return []

    adapters = []
    current = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("Name:"):
            if current.get("name"):
                adapters.append(current)
            current = {"name": line.split(":", 1)[1].strip()}
        elif line.startswith("IPAddress:"):
            current["ip"] = line.split(":", 1)[1].strip()
        elif line.startswith("NetworkMask:"):
            current["netmask"] = line.split(":", 1)[1].strip()
    if current.get("name"):
        adapters.append(current)

    return adapters


# ── CLI Helpers ─────────────────────────────────────────────────────────────

def header(text):
    print()
    print("=" * 70)
    print(f"  {text}".center(70))
    print("=" * 70)


def section(text):
    print(f"\n--- {text} " + "-" * max(0, 66 - len(text)))


def prompt(msg, default=None):
    if default is not None:
        val = input(f"  {msg} [{default}]: ").strip()
        return val if val else str(default)
    return input(f"  {msg}: ").strip()


def prompt_int(msg, lo, hi, default=None):
    while True:
        raw = prompt(msg, default)
        try:
            n = int(raw)
            if lo <= n <= hi:
                return n
            print(f"    Enter {lo}-{hi}.")
        except ValueError:
            print("    Invalid number.")


def prompt_choice(msg, options):
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    return prompt_int(msg, 1, len(options)) - 1


def prompt_yn(msg, default="y"):
    return prompt(msg, default).lower() in ("y", "yes")


# ── Subnet Setup ────────────────────────────────────────────────────────────

def setup_subnets():
    """Create or reuse host-only adapters as subnets."""
    header("NETWORK SETUP")

    existing = get_hostonlyifs()
    if existing:
        print("\n  Existing host-only adapters:")
        for a in existing:
            print(f"    - {a['name']}  IP: {a.get('ip', 'N/A')}")

    num = prompt_int("How many subnets do you need?", 1, 4, 2)

    subnets = []
    for i in range(num):
        section(f"Subnet {i + 1}")

        # Reuse existing or create new?
        if existing:
            options = [f"{a['name']}  (IP: {a.get('ip', 'N/A')})" for a in existing]
            options.append("Create new adapter")
            idx = prompt_choice("  Pick adapter", options)

            if idx < len(existing):
                adapter = existing[idx]
                name = prompt("  Subnet name", f"Subnet_{i+1}")
                subnets.append({
                    "name": name,
                    "adapter": adapter["name"],
                    "ip": adapter.get("ip", ""),
                })
                # Remove from list so it can't be picked again
                existing.pop(idx)
                print(f"  [OK] {name} -> {adapter['name']}")
                continue

        # Create new
        name = prompt("  Subnet name", f"Subnet_{i+1}")
        base = prompt(f"  IP prefix (e.g., 192.168.{30 + i*10})",
                       f"192.168.{30 + i*10}")
        gateway = f"{base}.1"

        # Create adapter
        out = vbox(["hostonlyif", "create"])
        if not out or "successfully created" not in out:
            print("  [ERROR] Failed to create adapter")
            continue

        adapter_name = ""
        for line in out.splitlines():
            if "'" in line:
                adapter_name = line.split("'")[1]
                break

        if adapter_name:
            vbox(["hostonlyif", "ipconfig", adapter_name,
                  "--ip", gateway, "--netmask", "255.255.255.0"])

            # DHCP
            if prompt_yn("  Enable DHCP?", "y"):
                net_name = f"HostInterfaceNetworking-{adapter_name}"
                vbox(["dhcpserver", "remove", "--network", net_name], check=False)
                vbox(["dhcpserver", "add",
                      "--network", net_name,
                      "--server-ip", f"{base}.2",
                      "--netmask", "255.255.255.0",
                      "--lower-ip", f"{base}.100",
                      "--upper-ip", f"{base}.200",
                      "--enable"])
                print(f"  [OK] DHCP: {base}.100 - {base}.200")

            subnets.append({
                "name": name,
                "adapter": adapter_name,
                "ip": gateway,
            })
            print(f"  [OK] {name} -> {adapter_name} ({gateway})")

    return subnets


# ── VM Selection & Assignment ───────────────────────────────────────────────

def assign_vms(subnets):
    """Let user pick existing VMs and assign them to subnets."""
    header("VM ASSIGNMENT")

    all_vms = get_registered_vms()
    if not all_vms:
        print("  No VMs registered in VirtualBox.")
        return [], None

    # Show available VMs
    section("Registered VMs")
    for i, vm in enumerate(all_vms, 1):
        state_tag = "[RUNNING]" if vm["state"] == "running" else "[OFF]"
        print(f"    {i}. {vm['name']:25s}  {state_tag:10s}  "
              f"OS: {vm['ostype']}  RAM: {vm['memory']}MB")

    # Tag each VM as endpoint, firewall, or skip
    section("Classify VMs")
    print("  Tag each VM you want to use.\n")

    endpoints = []
    firewalls = []
    used_vm_names = set()
    roles = ["endpoint", "firewall", "skip (don't use)"]

    for vm in all_vms:
        print(f"  {vm['name']}:")
        idx = prompt_choice("  Role", roles)
        if idx == 0:
            endpoints.append(vm)
            used_vm_names.add(vm["name"])
        elif idx == 1:
            firewalls.append(vm)
            used_vm_names.add(vm["name"])
        # idx == 2 → skip

    if not endpoints:
        print("\n  [WARN] No endpoint VMs selected.")

    # Assign endpoints to subnets
    section("Assign Endpoints to Subnets")
    vm_assignments = []  # list of (vm_name, subnet_name, adapter_name)

    for vm in endpoints:
        print(f"\n  VM: {vm['name']}")
        print("  Which subnet(s)?")
        num_nics = prompt_int(f"  How many subnets for '{vm['name']}'?",
                              1, min(4, len(subnets)), 1)

        available = list(range(len(subnets)))
        for n in range(num_nics):
            labels = [f"{subnets[j]['name']} ({subnets[j]['ip']})"
                      for j in available]
            idx_in_list = prompt_choice(f"  NIC {n+1}", labels)
            actual = available[idx_in_list]
            vm_assignments.append((vm["name"], subnets[actual], n + 1))
            available.remove(actual)

    # Firewall setup
    fw_config = None
    if firewalls and len(subnets) >= 2:
        section("Firewall Routing")

        if len(firewalls) == 1:
            fw = firewalls[0]
            print(f"  Using: {fw['name']}")
        else:
            labels = [fw["name"] for fw in firewalls]
            fi = prompt_choice("  Which firewall VM?", labels)
            fw = firewalls[fi]

        # WAN
        subnet_labels = [f"{s['name']} ({s['ip']})" for s in subnets]
        print("\n  Select WAN subnet:")
        wan_idx = prompt_choice("  WAN", subnet_labels)

        # LAN = everything else
        lan_subnets = [s for i, s in enumerate(subnets) if i != wan_idx]
        lan_names = [s["name"] for s in lan_subnets]
        print(f"  LAN subnets: {', '.join(lan_names)}")

        fw_config = {
            "vm": fw,
            "wan": subnets[wan_idx],
            "lans": lan_subnets,
        }
    elif firewalls and len(subnets) < 2:
        print("\n  [WARN] Firewall needs 2+ subnets. Only 1 subnet selected.")

    return vm_assignments, fw_config


# ── Deploy ──────────────────────────────────────────────────────────────────

def deploy(subnets, vm_assignments, fw_config):
    """Wire NICs and start VMs."""
    header("DEPLOY")

    # Wire endpoint NICs
    section("Connecting VMs to subnets")
    for vm_name, subnet, nic_num in vm_assignments:
        adapter = subnet["adapter"]
        print(f"  {vm_name} NIC{nic_num} -> {subnet['name']} ({adapter})")
        result = vbox(["modifyvm", vm_name,
                       f"--nic{nic_num}=hostonly",
                       f"--host-only-adapter{nic_num}={adapter}"])
        if result is not None:
            vbox(["modifyvm", vm_name, f"--nic-promisc{nic_num}=allow-all"])
            print(f"    [OK]")
        else:
            print(f"    [FAIL]")

    # Wire firewall NICs
    if fw_config:
        section("Connecting firewall")
        fw_name = fw_config["vm"]["name"]

        # NIC 1 = WAN
        wan_adapter = fw_config["wan"]["adapter"]
        print(f"  {fw_name} NIC1 (WAN) -> {fw_config['wan']['name']} ({wan_adapter})")
        vbox(["modifyvm", fw_name, "--nic1=hostonly",
              f"--host-only-adapter1={wan_adapter}"])
        vbox(["modifyvm", fw_name, "--nic-promisc1=allow-all"])

        # NIC 2+ = LAN
        for i, lan in enumerate(fw_config["lans"]):
            nic = i + 2
            print(f"  {fw_name} NIC{nic} (LAN) -> {lan['name']} ({lan['adapter']})")
            vbox(["modifyvm", fw_name, f"--nic{nic}=hostonly",
                  f"--host-only-adapter{nic}={lan['adapter']}"])
            vbox(["modifyvm", fw_name, f"--nic-promisc{nic}=allow-all"])

    # Review
    section("Topology")
    if fw_config:
        fw_name = fw_config["vm"]["name"]

        # WAN side VMs
        wan_name = fw_config["wan"]["name"]
        wan_vms = [v for v, s, _ in vm_assignments if s["name"] == wan_name]
        for v in wan_vms:
            print(f"    [{v}]")
            print(f"        |")
        print(f"        | ({wan_name})")
        print(f"        |")
        print(f"    [{fw_name}]")

        for lan in fw_config["lans"]:
            print(f"        |")
            print(f"        | ({lan['name']})")
            print(f"        |")
            lan_vms = [v for v, s, _ in vm_assignments if s["name"] == lan["name"]]
            for v in lan_vms:
                print(f"    [{v}]")
    else:
        for vm_name, subnet, nic_num in vm_assignments:
            print(f"    [{vm_name}] -- {subnet['name']}")

    # Start
    section("Start VMs")
    if not prompt_yn("Start VMs now?", "y"):
        print("  Skipped. VMs are wired but not started.")
        return

    headless = prompt_yn("Headless mode?", "n")
    mode = "headless" if headless else "gui"

    # Start firewall first
    if fw_config:
        fw_name = fw_config["vm"]["name"]
        print(f"  Starting {fw_name} ({mode})...")
        vbox(["startvm", fw_name, "--type", mode])

    # Then endpoints
    started = set()
    if fw_config:
        started.add(fw_config["vm"]["name"])

    for vm_name, _, _ in vm_assignments:
        if vm_name not in started:
            print(f"  Starting {vm_name} ({mode})...")
            vbox(["startvm", vm_name, "--type", mode])
            started.add(vm_name)

    # Status
    section("Status")
    all_names = started
    for name in all_names:
        info = vbox(["showvminfo", name, "--machinereadable"], check=False) or ""
        state = "unknown"
        for line in info.splitlines():
            if line.startswith("VMState="):
                state = line.split("=")[1].strip('"')
                break
        tag = "[RUNNING]" if state == "running" else f"[{state.upper()}]"
        print(f"    {tag:12s}  {name}")

    if headless:
        print("\n  VMs running headless. Use this tool or VirtualBox Manager to stop them.")

    print("\n  Done.")


# ── Stop / Status ───────────────────────────────────────────────────────────

def stop_menu():
    """Stop running VMs."""
    header("STOP VMs")

    raw = vbox(["list", "runningvms"], check=False) or ""
    running = []
    for line in raw.splitlines():
        if '"' in line:
            running.append(line.split('"')[1])

    if not running:
        print("  No VMs running.")
        return

    print(f"  {len(running)} VM(s) running:\n")
    options = running + ["Stop ALL", "Cancel"]
    idx = prompt_choice("Which to stop?", options)

    if idx == len(options) - 1:  # Cancel
        return

    force = prompt_yn("Force power off? (y=instant, n=graceful ACPI)", "n")
    action = "poweroff" if force else "acpipowerbutton"

    if idx == len(options) - 2:  # Stop ALL
        for name in running:
            print(f"  Stopping {name}...")
            vbox(["controlvm", name, action])
        print(f"\n  Stopped {len(running)} VMs.")
    else:
        name = running[idx]
        print(f"  Stopping {name}...")
        vbox(["controlvm", name, action])


def status_menu():
    """Show all VMs and their state."""
    header("VM STATUS")

    all_vms = get_registered_vms()
    if not all_vms:
        print("  No VMs registered.")
        return

    for vm in all_vms:
        state = vm["state"]
        tag = "[RUNNING]" if state == "running" else f"[{state.upper()}]"
        nics = []
        for n in range(1, 5):
            nic = vm.get(f"nic{n}", "none")
            if nic != "none":
                nics.append(f"NIC{n}:{nic}")
        nic_str = "  ".join(nics) if nics else "(no NICs)"
        print(f"    {tag:12s}  {vm['name']:25s}  {nic_str}")


# ── Main Menu ───────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(VBOX):
        print(f"VBoxManage not found at: {VBOX}")
        sys.exit(1)

    os.system("cls" if os.name == "nt" else "clear")
    header("LAB BUILDER - Existing VMs")
    print("  Use VMs already in VirtualBox. No new VMs created.")

    while True:
        section("Main Menu")
        print("    1. Build Lab  (pick VMs -> assign subnets -> wire firewall -> start)")
        print("    2. VM Status")
        print("    3. Stop VMs")
        print("    4. Quit")

        choice = prompt_int("Choose", 1, 4)

        if choice == 1:
            subnets = setup_subnets()
            if not subnets:
                print("  No subnets configured.")
                continue
            vm_assignments, fw_config = assign_vms(subnets)
            if not vm_assignments and not fw_config:
                print("  Nothing to deploy.")
                continue
            deploy(subnets, vm_assignments, fw_config)

        elif choice == 2:
            status_menu()

        elif choice == 3:
            stop_menu()

        elif choice == 4:
            print("  Bye.")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()
