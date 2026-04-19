#!/usr/bin/env python3
"""
Network Simulation Orchestrator - Interactive CLI entry point.

Usage: python cli.py
"""

import os
import sys
import subprocess

import vbox
import config_store
import deployer
import validator
import vm_manager
import prebuilt
from models import (OS_TYPES, LabConfig, Subnet, DHCPConfig,
                    VMConfig, FirewallConfig, ImageInfo, guess_ostype)
from ssh_manager import SSHManager
from logger import get_logger

log = get_logger()


# ── CLI Helpers ─────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header(text):
    w = 70
    print()
    print("=" * w)
    print(f"  {text}".center(w))
    print("=" * w)


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
            print(f"    Please enter {lo}-{hi}.")
        except ValueError:
            print("    Invalid number.")


def prompt_choice(msg, options):
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    return prompt_int(msg, 1, len(options)) - 1


def prompt_yn(msg, default="y"):
    val = prompt(msg, default)
    return val.lower() in ("y", "yes")


# ── ISO Management ──────────────────────────────────────────────────────────

class ImageManager:
    """Handles scanning, classification, and tracking of OVA appliances."""

    TYPE_LABELS = {"ova": "OVA", "vbox": "VM"}

    def __init__(self):
        self.images = []
        self.used = set()  # filenames already assigned to a VM

    def scan(self, directory=None):
        """Scan for OVA appliances and load saved roles."""
        self.images = config_store.scan_images(directory)
        return len(self.images) > 0

    def classify_new(self):
        """Ask user to classify any OVAs that don't have a saved role."""
        new_imgs = [img for img in self.images if not img.role]
        if not new_imgs:
            print("  All OVAs already classified.")
            return

        section("Classify new OVAs")
        print("  Tag each as 'endpoint' or 'firewall'.")
        print("  This is saved so you won't be asked again.\n")
        roles = ["endpoint", "firewall"]
        saved = config_store.load_iso_roles()

        for img in new_imgs:
            print(f"  {img.filename}:")
            idx = prompt_choice("  Role", roles)
            img.role = roles[idx]
            saved[img.filename] = img.role

        config_store.save_iso_roles(saved)
        print("\n  Roles saved.")

    def reclassify(self):
        """Let user change existing classifications."""
        roles = ["endpoint", "firewall"]
        saved = config_store.load_iso_roles()
        labels = [f"{img.filename}  (currently: {img.role})"
                  for img in self.images]

        while True:
            print()
            idx = prompt_choice("  Which OVA?", labels)
            print(f"  {self.images[idx].filename}:")
            ri = prompt_choice("  New role", roles)
            self.images[idx].role = roles[ri]
            saved[self.images[idx].filename] = roles[ri]
            labels[idx] = f"{self.images[idx].filename}  (currently: {roles[ri]})"
            if not prompt_yn("Re-classify another?", "n"):
                break

        config_store.save_iso_roles(saved)

    def get_available(self, role):
        """Get unused images of a given role."""
        return [img for img in self.images
                if img.role == role and img.filename not in self.used]

    def mark_used(self, img):
        """Mark an image as used for this session."""
        self.used.add(img.filename)

    def display(self):
        """Show all available images with role."""
        section("Available Images")
        for i, img in enumerate(self.images, 1):
            kind = self.TYPE_LABELS.get(img.image_type, "?")
            tag = f"[{img.role}]" if img.role else "[unclassified]"
            used = " (IN USE)" if img.filename in self.used else ""
            print(f"    {i}. {img.filename}  ({img.size_mb} MB)  "
                  f"{kind}  {tag}{used}")

    def pick_image(self, role, label="Select image"):
        """Let user pick an unused image of the given role. Returns ImageInfo or None."""
        available = self.get_available(role)
        if not available:
            print(f"  No available {role} images.")
            return None
        labels = [f"{img.filename}  ({img.size_mb} MB)  "
                  f"[{self.TYPE_LABELS.get(img.image_type, '?')}]"
                  for img in available]
        print(f"\n  {label} ({role} images):")
        idx = prompt_choice("  Image", labels)
        picked = available[idx]
        self.mark_used(picked)
        return picked


# ── Prebuilt Mode ───────────────────────────────────────────────────────────

def run_prebuilt():
    """Prebuilt mode: fully automated, user just picks a scenario."""
    header("PREBUILT MODE")

    print("\n  Select a pre-configured scenario. Everything is set up automatically —")
    print("  subnets, VMs, and firewall. No configuration needed.\n")

    scenarios = prebuilt.SCENARIOS

    # Display scenarios with availability
    for i, sc in enumerate(scenarios, 1):
        ok, missing = prebuilt.check_scenario(sc)
        status = "READY" if ok else "MISSING IMAGES"
        print(f"  {'-' * 66}")
        print(f"  {i}. {sc['name']}  [{status}]")
        print(f"    {sc['description']}")
        print(f"\n    Layout:")
        print(f"    {sc['layout']}")
        if not ok:
            print(f"\n    Missing: {', '.join(missing)}")
        print()

    print(f"  {'-' * 66}")
    print(f"  {len(scenarios) + 1}. Back to menu")

    idx = prompt_int("Choose scenario", 1, len(scenarios) + 1)

    if idx == len(scenarios) + 1:
        return None

    scenario = scenarios[idx - 1]

    # Check availability
    ok, missing = prebuilt.check_scenario(scenario)
    if not ok:
        print(f"\n  Cannot deploy — missing images:")
        for m in missing:
            print(f"    - {m}")
        print("  Please add the required OVA files or register the source VMs.")
        return None

    # Build config
    print(f"\n  Loading scenario: {scenario['name']}...")
    config = prebuilt.build_scenario_config(scenario)
    if not config:
        print("  Failed to build scenario config.")
        return None

    return config


# ── Custom Mode ─────────────────────────────────────────────────────────────

def _show_custom_topology(subnets, vms, firewalls):
    """Show a live preview of the network being built."""
    if not subnets:
        return
    print("\n  Current topology:")
    fw_names = {fw.vm_name for fw in firewalls}

    # Group VMs by subnet
    subnet_vms = {}
    for vm in vms:
        if vm.name in fw_names:
            continue
        for sn in vm.subnets:
            subnet_vms.setdefault(sn, []).append(vm.name)

    # Build connectivity map from firewalls
    connected = set()  # pairs of subnet names connected by a firewall
    for fw in firewalls:
        all_fw_subs = [fw.wan_subnet] + fw.lan_subnets
        for a in all_fw_subs:
            for b in all_fw_subs:
                if a != b:
                    connected.add((min(a, b), max(a, b)))

    for s in subnets:
        vm_list = subnet_vms.get(s.name, [])
        vm_str = ", ".join(vm_list) if vm_list else "(empty)"
        print(f"    [{s.name}] {s.network}  VMs: {vm_str}")

    if firewalls:
        print()
        for fw in firewalls:
            print(f"    [{fw.vm_name}] bridges: "
                  f"{fw.wan_subnet} <-> {', '.join(fw.lan_subnets)}")

    # Show connectivity
    if len(subnets) >= 2:
        print()
        subnet_names = [s.name for s in subnets]
        for i in range(len(subnet_names)):
            for j in range(i + 1, len(subnet_names)):
                a, b = subnet_names[i], subnet_names[j]
                pair = (min(a, b), max(a, b))
                if pair in connected:
                    print(f"    {a} <-> {b}  CONNECTED (via firewall)")
                else:
                    print(f"    {a} <-> {b}  ISOLATED (no firewall between them)")


def run_custom(img_mgr):
    """Custom mode: guided educational walkthrough."""
    header("CUSTOM BUILD MODE")

    print("""
  Welcome! This will walk you through building a virtual network
  step by step. Don't worry if you're new to networking — each step
  explains what's happening and why.

  You'll set up:
    1. Subnets    — separate network segments (like rooms in a building)
    2. VMs        — virtual machines placed on those subnets
    3. Firewalls  — devices that connect subnets and control traffic
  """)

    input("  Press Enter to start...")

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 1: SUBNETS
    # ═══════════════════════════════════════════════════════════════════
    section("Step 1: Create Subnets")

    print("""
  A SUBNET is an isolated network segment. Think of it like a room:

    - Machines in the SAME subnet can talk to each other freely
    - Machines in DIFFERENT subnets CANNOT communicate
      (unless a firewall/router connects them)

  Example: In an office, you might have:
    - "LAN" subnet for employee computers
    - "DMZ" subnet for public-facing servers
    - "WAN" subnet for the outside world

  Tip: Start with 2 subnets to keep things simple. You can go up to 5.
  """)

    num_subnets = prompt_int("How many subnets?", 1, 5, 2)

    subnets = []
    suggested_names = ["WAN", "LAN", "DMZ", "MGMT", "DEV"]
    for i in range(num_subnets):
        default_name = suggested_names[i] if i < len(suggested_names) else f"Subnet_{i+1}"
        base = f"192.168.{30 + i*10}"

        print(f"\n  --- Subnet {i+1} of {num_subnets} ---")
        name = prompt("  Subnet name", default_name)

        # Auto-configure everything with sensible defaults
        gateway = f"{base}.1"
        dhcp = DHCPConfig(
            enabled=True, server_ip=f"{base}.2",
            netmask="255.255.255.0",
            lower_ip=f"{base}.100", upper_ip=f"{base}.200",
        )

        subnets.append(Subnet(
            name=name, network=f"{base}.0/24",
            gateway_ip=gateway, netmask="255.255.255.0", dhcp=dhcp,
        ))
        print(f"  [OK] {name}: {base}.0/24")
        print(f"       Machines on this subnet get IPs: {base}.100 - {base}.200")

    if num_subnets >= 2:
        print(f"\n  Remember: {subnets[0].name} and {subnets[1].name} are ISOLATED.")
        print(f"  Machines on {subnets[0].name} cannot reach {subnets[1].name} yet.")
        print(f"  We'll add firewalls later to connect them (if you want).")

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 2: VMs
    # ═══════════════════════════════════════════════════════════════════
    section("Step 2: Place VMs on Subnets")

    print(f"""
  Now let's add virtual machines to your subnets.

  Two types of VMs:
    - ENDPOINT:  Regular machines (servers, desktops, attackers)
    - FIREWALL:  Connects subnets and controls traffic between them

  Tip: Place at least one endpoint on each subnet so you can test
  connectivity between them.
  """)

    # Show available images
    print("  Available VM images:")
    for i, img in enumerate(img_mgr.images, 1):
        kind = img_mgr.TYPE_LABELS.get(img.image_type, "?")
        tag = f"[{img.role}]" if img.role else "[unclassified]"
        print(f"    {i}. {img.filename}  ({img.size_mb} MB)  {kind}  {tag}")
    print()

    num_vms = prompt_int("How many VMs to deploy?", 1, 10, min(num_subnets + 1, 4))

    vms = []
    for v in range(num_vms):
        print(f"\n  --- VM {v+1} of {num_vms} ---")

        # Role
        roles = ["endpoint", "firewall"]
        if num_subnets >= 2:
            print("  What type of VM is this?")
            print("    endpoint  = a regular machine (server, desktop, attacker)")
            print("    firewall  = connects subnets together (like pfSense)")
        role_idx = prompt_choice("  Role", roles)
        role = roles[role_idx]

        # Pick image
        img = img_mgr.pick_image(role, f"Select image for VM {v+1}")
        if not img:
            print("  No images available for this role. Skipping.")
            continue

        name = prompt("  VM name", f"VM{v+1}")

        # Subnet assignment
        if role == "firewall":
            print(f"\n  A firewall connects multiple subnets.")
            print(f"  Select which subnets this firewall will bridge:")
            assigned = []
            subnet_labels = [f"{s.name} ({s.network})" for s in subnets]
            num_nics = prompt_int(f"  How many subnets?", 2, min(4, len(subnets)),
                                  min(2, len(subnets)))
            available = list(range(len(subnets)))
            for n in range(num_nics):
                remaining = [subnet_labels[j] for j in available]
                idx_in_remaining = prompt_choice(
                    f"  NIC {n+1} ({'WAN' if n == 0 else 'LAN'})", remaining)
                actual_idx = available[idx_in_remaining]
                assigned.append(subnets[actual_idx].name)
                available.remove(actual_idx)
        else:
            print(f"\n  Which subnet should this VM be on?")
            subnet_labels = [f"{s.name} ({s.network})" for s in subnets]
            idx = prompt_choice("  Subnet", subnet_labels)
            assigned = [subnets[idx].name]

        vms.append(VMConfig(
            name=name, ostype=img.ostype if img else "Other_64",
            ram_mb=img.size_mb if img and img.size_mb > 256 else 2048,
            cpus=2, disk_mb=0,
            iso_path=img.path if img else "",
            image_type=img.image_type if img else "ova",
            role=role, subnets=assigned,
        ))
        print(f"  [OK] {name} ({role}) -> {', '.join(assigned)}")

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 3: FIREWALLS
    # ═══════════════════════════════════════════════════════════════════
    config = LabConfig(subnets=subnets, vms=vms)

    firewall_vms = [vm for vm in vms if vm.role == "firewall"]

    if firewall_vms and len(subnets) >= 2:
        section("Step 3: Configure Firewall Routing")

        print("""
  Each firewall has a WAN side (external/untrusted) and one or more
  LAN sides (internal/protected).

  Default pfSense rules:
    - LAN -> WAN traffic: ALLOWED
    - WAN -> LAN traffic: BLOCKED
    - You can change these rules in the pfSense web GUI after deployment
  """)

        for fw_vm in firewall_vms:
            print(f"\n  Configuring: {fw_vm.name}")
            print(f"  This firewall is connected to: {', '.join(fw_vm.subnets)}")

            if len(fw_vm.subnets) < 2:
                print(f"  Warning: A firewall needs at least 2 subnets to be useful.")
                continue

            # WAN is first subnet assigned, LAN is the rest
            wan_sub = fw_vm.subnets[0]
            lan_subs = fw_vm.subnets[1:]

            print(f"  WAN (external): {wan_sub}")
            print(f"  LAN (internal): {', '.join(lan_subs)}")

            if not prompt_yn(f"  Is this correct?", "y"):
                # Let user pick WAN
                subnet_labels = [f"{s} ({'WAN' if s == wan_sub else 'LAN'})"
                                 for s in fw_vm.subnets]
                wan_idx = prompt_choice("  Which subnet is WAN?", fw_vm.subnets)
                wan_sub = fw_vm.subnets[wan_idx]
                lan_subs = [s for s in fw_vm.subnets if s != wan_sub]

            config.firewalls.append(FirewallConfig(
                vm_name=fw_vm.name,
                wan_subnet=wan_sub,
                lan_subnets=lan_subs,
            ))
            print(f"  [OK] {fw_vm.name}: WAN={wan_sub}, LAN={', '.join(lan_subs)}")

    elif len(subnets) >= 2 and not firewall_vms:
        section("Step 3: Firewall Setup")
        print(f"\n  You have {len(subnets)} subnets but no firewall VMs.")
        print(f"  Without a firewall, your subnets are completely isolated.")
        print(f"  Machines on {subnets[0].name} CANNOT reach {subnets[1].name}.")
        print(f"\n  That's fine if you want isolated networks!")
        print(f"  If you want them to communicate, go back and add a firewall VM.")
    else:
        section("Step 3: Firewall Setup")
        print(f"\n  Only 1 subnet — all VMs can communicate directly.")
        print(f"  No firewall needed!")

    # ═══════════════════════════════════════════════════════════════════
    # PREVIEW
    # ═══════════════════════════════════════════════════════════════════
    section("Network Preview")
    _show_custom_topology(subnets, vms, config.firewalls)

    return config


# ── Review & Topology ───────────────────────────────────────────────────────

def review_config(config):
    """Display the full config and ASCII topology."""
    header("REVIEW")

    section("Subnets")
    for s in config.subnets:
        dhcp_str = ""
        if s.dhcp and s.dhcp.enabled:
            dhcp_str = f"  DHCP: {s.dhcp.lower_ip}-{s.dhcp.upper_ip}"
        print(f"    {s.name:15s}  {s.network:20s}  gw={s.gateway_ip}{dhcp_str}")

    section("VMs")
    type_labels = {"ova": "OVA", "vbox": "VM"}
    for vm in config.vms:
        img_name = os.path.basename(vm.iso_path) if vm.iso_path else "(none)"
        img_type = type_labels.get(getattr(vm, "image_type", "ova"), "?")
        nets = ", ".join(vm.subnets) if vm.subnets else "(none)"
        print(f"    [{vm.role:8s}]  {vm.name:20s}  RAM={vm.ram_mb}MB  "
              f"CPUs={vm.cpus}")
        print(f"               Image: {img_name}  [{img_type}]")
        print(f"               Subnets: {nets}")

    if config.firewalls:
        section("Firewall Routing")
        for i, fw in enumerate(config.firewalls, 1):
            if len(config.firewalls) > 1:
                print(f"    Firewall {i}:")
                print(f"      VM:  {fw.vm_name}")
                print(f"      WAN: {fw.wan_subnet}")
                print(f"      LAN: {', '.join(fw.lan_subnets)}")
            else:
                print(f"    VM:  {fw.vm_name}")
                print(f"    WAN: {fw.wan_subnet}")
                print(f"    LAN: {', '.join(fw.lan_subnets)}")

    # ASCII topology
    draw_topology(config)

    # Validation
    errors = validator.validate_lab(config)
    if errors:
        section("VALIDATION ERRORS")
        for e in errors:
            print(f"    ! {e}")
    else:
        print("\n  Validation: PASSED")


def draw_topology(config):
    """Draw ASCII topology diagram."""
    section("Topology")

    fw_names = {fw.vm_name for fw in config.firewalls}

    if not config.firewalls:
        # No firewalls: just list VMs per subnet
        subnet_vms = {}
        for vm in config.vms:
            for sn in vm.subnets:
                subnet_vms.setdefault(sn, []).append(vm.name)
        for sn, names in subnet_vms.items():
            print(f"    [{sn}]: {', '.join(names)}")
        return

    # Group non-firewall VMs by subnet
    subnet_vms = {}
    for vm in config.vms:
        if vm.name in fw_names:
            continue
        for sn in vm.subnets:
            subnet_vms.setdefault(sn, []).append(vm.name)

    # Build a chain: find which subnets connect through which firewalls
    # Show each firewall with its connected subnets
    shown_subnets = set()

    for fw in config.firewalls:
        # WAN side (only show VMs if not already shown)
        if fw.wan_subnet not in shown_subnets:
            wan_vms = subnet_vms.get(fw.wan_subnet, [])
            for name in wan_vms:
                print(f"    [{name}]")
                print(f"        |")
            print(f"        | ({fw.wan_subnet})")
            print(f"        |")
            shown_subnets.add(fw.wan_subnet)

        print(f"    [{fw.vm_name}]")

        # LAN sides
        for lan in fw.lan_subnets:
            print(f"        |")
            print(f"        | ({lan})")
            print(f"        |")
            if lan not in shown_subnets:
                lan_vms = subnet_vms.get(lan, [])
                for name in lan_vms:
                    print(f"    [{name}]")
                shown_subnets.add(lan)


# ── Stop / Delete ───────────────────────────────────────────────────────────

def stop_menu():
    """Interactive stop menu."""
    header("STOP VMs")

    raw = vm_manager.list_running_vms()
    if not raw or not raw.strip():
        print("  No VMs currently running.")
        return

    running = []
    for line in raw.splitlines():
        if '"' in line:
            running.append(line.split('"')[1])

    if not running:
        print("  No VMs currently running.")
        return

    print(f"  {len(running)} VM(s) running:\n")
    options = [name for name in running]
    options.append("Stop ALL")
    options.append("Cancel")

    idx = prompt_choice("Which VM to stop?", options)

    if idx == len(options) - 1:  # Cancel
        return
    if idx == len(options) - 2:  # Stop ALL
        force = prompt_yn("Force power off? (y=instant, n=graceful)", "n")
        for name in running:
            vm_manager.stop_vm(name, force=force)
        print(f"\n  Stopped {len(running)} VMs.")
    else:
        force = prompt_yn("Force power off?", "n")
        vm_manager.stop_vm(running[idx], force=force)


def _is_vbox_source(vm_name):
    """Check if a VM's files live inside our project directory (i.e. it's a
    .vbox source VM that should only be unregistered, not deleted)."""
    info = vbox.run(["showvminfo", vm_name, "--machinereadable"], check=False)
    if not info:
        return False
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for line in info.splitlines():
        if line.startswith("CfgFile="):
            cfg = line.split("=", 1)[1].strip('"')
            return os.path.normcase(cfg).startswith(os.path.normcase(base_dir))
    return False


def delete_menu():
    """Interactive delete menu."""
    header("DELETE VMs")

    raw = vm_manager.list_vms()
    if not raw or not raw.strip():
        print("  No VMs registered.")
        return

    all_vms = []
    for line in raw.splitlines():
        if '"' in line:
            name = line.split('"')[1]
            state = vm_manager.get_vm_state(name)
            all_vms.append((name, state))

    if not all_vms:
        print("  No VMs registered.")
        return

    options = [f"{name}  [{state}]" for name, state in all_vms]
    options.append("Delete ALL")
    options.append("Cancel")

    idx = prompt_choice("Which VM to delete?", options)

    if idx == len(options) - 1:  # Cancel
        return
    if idx == len(options) - 2:  # Delete ALL
        confirm = prompt("Type 'yes' to delete ALL VMs and their files", "no")
        if confirm != "yes":
            print("  Cancelled.")
            return
        for name, state in all_vms:
            if state == "running":
                vm_manager.stop_vm(name, force=True)
            keep = _is_vbox_source(name)
            vm_manager.delete_vm(name, keep_files=keep)
            if keep:
                print(f"    (unregistered '{name}' — source files preserved)")
        print(f"\n  Deleted {len(all_vms)} VMs.")
    else:
        name, state = all_vms[idx]
        confirm = prompt(f"Type 'yes' to delete '{name}'", "no")
        if confirm != "yes":
            print("  Cancelled.")
            return
        if state == "running":
            vm_manager.stop_vm(name, force=True)
        keep = _is_vbox_source(name)
        vm_manager.delete_vm(name, keep_files=keep)
        if keep:
            print(f"  (unregistered — source files preserved)")


# ── SSH Interaction ─────────────────────────────────────────────────────────

def get_vm_mac(vm_name, nic=1):
    """Get a VM's MAC address from VBoxManage for a given NIC."""
    info = vbox.run(["showvminfo", vm_name, "--machinereadable"], check=False)
    if not info:
        return None
    key = f"macaddress{nic}"
    for line in info.splitlines():
        if line.lower().startswith(key + "="):
            raw = line.split("=", 1)[1].strip('"')
            # VBox returns MAC without separators (e.g. "080027A1B2C3")
            # Format it as "08-00-27-a1-b2-c3" to match Windows arp -a output
            mac = "-".join(raw[i:i+2] for i in range(0, len(raw), 2)).lower()
            return mac
    return None


def refresh_arp_for_subnet(subnet):
    """Ping the subnet broadcast and gateway to populate the ARP table."""
    # Extract base from network (e.g. "192.168.30.0/24" → "192.168.30")
    base = subnet.network.rsplit(".", 1)[0]
    broadcast = f"{base}.255"

    # Ping broadcast + gateway to wake up ARP entries
    for target in [broadcast, subnet.gateway_ip]:
        subprocess.run(["ping", "-n", "2", "-w", "500", target],
                       capture_output=True, creationflags=0x08000000)

    # Also ping the DHCP range (quick sweep) to catch assigned IPs
    if subnet.dhcp and subnet.dhcp.enabled:
        lower = int(subnet.dhcp.lower_ip.rsplit(".", 1)[1])
        upper = int(subnet.dhcp.upper_ip.rsplit(".", 1)[1])
        # Limit sweep to keep it fast
        step = max(1, (upper - lower) // 20)
        for i in range(lower, upper + 1, step):
            ip = f"{base}.{i}"
            subprocess.run(["ping", "-n", "1", "-w", "300", ip],
                           capture_output=True, creationflags=0x08000000)


def get_arp_table():
    """Parse Windows 'arp -a' output into a dict of {mac: ip}."""
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
        mac_to_ip = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1].count("-") == 5:
                ip = parts[0]
                mac = parts[1].lower()
                mac_to_ip[mac] = ip
        return mac_to_ip
    except Exception:
        return {}


def discover_vm_ips(config):
    """
    Discover IP addresses for all running VMs using MAC address + ARP table.
    Retries up to 3 times for VMs that haven't obtained a DHCP lease yet.
    Returns dict of {vm_name: ip_address}.
    """
    import time

    # Collect MACs for all running VMs upfront
    running_vms = []
    for vm in config.vms:
        state = vm_manager.get_vm_state(vm.name)
        if state != "running":
            continue
        mac = get_vm_mac(vm.name, 1)
        running_vms.append((vm.name, mac))

    if not running_vms:
        print("  No running VMs found.")
        return {}

    print(f"  Discovering IP addresses for {len(running_vms)} VM(s)...")
    print("  Waiting for VMs to obtain DHCP leases...")

    vm_ips = {}
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        # Find which VMs still need IPs
        missing = [(name, mac) for name, mac in running_vms
                    if name not in vm_ips and mac]

        if not missing:
            break

        if attempt > 1:
            print(f"  Retry {attempt}/{max_attempts} — waiting 10s for DHCP...")
            time.sleep(10)

        # Ping every IP in each subnet's DHCP range
        print(f"  Scanning subnets...", end="", flush=True)
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
        print(" done.")

        # Read ARP table and match MACs
        arp = get_arp_table()
        for name, mac in missing:
            if mac in arp:
                vm_ips[name] = arp[mac]
                print(f"    {name} -> {arp[mac]}")

    # Report any still missing
    still_missing = [name for name, mac in running_vms if name not in vm_ips]
    if still_missing:
        print(f"\n  Could not detect IP for: {', '.join(still_missing)}")
        print("  (VM may still be booting or DHCP not configured inside the guest)")

    return vm_ips


def ping_from_host(ip):
    """Ping an IP from the host. Returns True if reachable."""
    result = subprocess.run(["ping", "-n", "3", "-w", "1000", ip],
                            capture_output=True, text=True,
                            creationflags=0x08000000)
    return result.returncode == 0


def check_port(ip, port, timeout=3):
    """Check if a TCP port is open. Returns True if connectable."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def scan_common_ports(ip):
    """Scan common service ports and return list of open ones."""
    ports = {
        22: "SSH",
        80: "HTTP",
        443: "HTTPS",
        21: "FTP",
        23: "Telnet",
        8080: "HTTP-Alt",
        8443: "HTTPS-Alt",
    }
    open_ports = {}
    for port, name in ports.items():
        if check_port(ip, port, timeout=2):
            open_ports[port] = name
    return open_ports


def connectivity_test(config):
    """Test connectivity between VMs by pinging from host and between VMs."""
    header("CONNECTIVITY TEST")

    # Discover IPs
    vm_ips = discover_vm_ips(config)

    if not vm_ips:
        print("\n  Could not detect any VM IP addresses.")
        print("  Make sure VMs have fully booted and obtained DHCP leases.")
        return vm_ips

    # Show discovered IPs
    section("Discovered IPs")
    for name, ip in vm_ips.items():
        print(f"    {name:25s} -> {ip}")

    not_found = [vm.name for vm in config.vms
                 if vm_manager.get_vm_state(vm.name) == "running"
                 and vm.name not in vm_ips]
    if not_found:
        print(f"\n  Could not detect IP for: {', '.join(not_found)}")

    # Build VM role lookup
    vm_roles = {vm.name: vm.role for vm in config.vms}

    # Ping + port scan each VM from the host
    section("Host -> VM Reachability")
    reachable = {}
    vm_ports = {}  # {vm_name: {port: service_name}}

    for name, ip in vm_ips.items():
        role = vm_roles.get(name, "endpoint")
        print(f"    {name} ({ip}):")

        # Ping test
        ping_ok = ping_from_host(ip)
        print(f"      Ping: {'OK' if ping_ok else 'blocked (normal for firewalls)' if role == 'firewall' else 'FAILED'}")

        # Port scan
        print(f"      Scanning ports...", end="", flush=True)
        ports = scan_common_ports(ip)
        vm_ports[name] = ports

        if ports:
            port_str = ", ".join(f"{p}/{svc}" for p, svc in sorted(ports.items()))
            print(f"  open: {port_str}")
        else:
            print(f"  no open ports detected")

        # Reachable if ping works OR any port is open
        reachable[name] = ping_ok or len(ports) > 0

        # Helpful hints
        if role == "firewall" and not ports:
            print(f"      Hint: Access pfSense console in VirtualBox GUI to configure interfaces")
        elif role == "firewall" and 443 in ports:
            print(f"      Web GUI: https://{ip}  (admin/pfsense)")
        elif role == "firewall" and 80 in ports:
            print(f"      Web GUI: http://{ip}  (admin/pfsense)")

        if role == "endpoint" and 22 not in ports:
            if 21 in ports:
                print(f"      Note: SSH not running, but FTP is open on port 21")
            else:
                print(f"      Note: SSH not running — enable it inside the VM")

    # Cross-VM connectivity
    # Note: We test from the host, not between VMs directly.
    # pfSense blocks host pings on WAN (normal) but still routes VM traffic.
    # So we check: same subnet = can communicate, different subnet = via firewall.
    endpoint_names = [vm.name for vm in config.vms if vm.role != "firewall"
                      and vm.name in vm_ips]
    if len(endpoint_names) >= 2:
        section("VM <-> VM Connectivity")

        # Build subnet lookup
        vm_subnet_map = {}
        for vm in config.vms:
            vm_subnet_map[vm.name] = set(vm.subnets)

        for i in range(len(endpoint_names)):
            for j in range(i + 1, len(endpoint_names)):
                name_a, name_b = endpoint_names[i], endpoint_names[j]
                subnets_a = vm_subnet_map.get(name_a, set())
                subnets_b = vm_subnet_map.get(name_b, set())
                shared = subnets_a & subnets_b

                if shared:
                    # Same subnet — VMs share a virtual switch, always reachable
                    both_up = reachable.get(name_a) and reachable.get(name_b)
                    status = "OK (same subnet)" if both_up else "FAILED"
                    print(f"    {name_a} <-> {name_b}  [{', '.join(shared)}]  {status}")
                elif config.firewalls:
                    # Find which firewall(s) bridge these subnets
                    bridging_fw = None
                    for fw in config.firewalls:
                        fw_subnets = {fw.wan_subnet} | set(fw.lan_subnets)
                        if (subnets_a & fw_subnets) and (subnets_b & fw_subnets):
                            bridging_fw = fw
                            break

                    if bridging_fw:
                        fw_ip = vm_ips.get(bridging_fw.vm_name)
                        if fw_ip:
                            print(f"    {name_a} <-> {name_b}  "
                                  f"[routed via {bridging_fw.vm_name}]  "
                                  f"OK — firewall routes between subnets")
                            wan_sub = bridging_fw.wan_subnet
                            a_side = "WAN" if wan_sub in subnets_a else "LAN"
                            b_side = "WAN" if wan_sub in subnets_b else "LAN"
                            print(f"      Default rules: LAN->WAN allowed, "
                                  f"WAN->LAN blocked")
                            print(f"      ({name_a} is on {a_side}, "
                                  f"{name_b} is on {b_side})")
                        else:
                            print(f"    {name_a} <-> {name_b}  "
                                  f"[via {bridging_fw.vm_name}]  "
                                  f"UNKNOWN — firewall IP not detected")
                    else:
                        # No single firewall bridges both subnets
                        print(f"    {name_a} <-> {name_b}  "
                              f"NO DIRECT ROUTE — no firewall connects "
                              f"these subnets")
                else:
                    print(f"    {name_a} <-> {name_b}  [different subnets, "
                          f"no firewall]  NO ROUTE")

    # Summary
    total = len(vm_ips)
    ok_count = sum(1 for v in reachable.values() if v)
    print(f"\n  Summary: {ok_count}/{total} VMs reachable from host.")

    # pfSense info — check LAN side for web GUI and SSH (all firewalls)
    if config.firewalls:
        import time as _time
        section("Firewall Access")
        for fw in config.firewalls:
            fw_name = fw.vm_name
            fw_wan_ip = vm_ips.get(fw_name)

            if len(config.firewalls) > 1:
                print(f"\n    {fw_name}:")
                indent = "      "
            else:
                indent = "    "

            if fw_wan_ip:
                print(f"{indent}WAN IP: {fw_wan_ip} (admin blocked on WAN — normal)")

            # Find LAN IP with retry
            fw_lan_ip = None
            if fw.lan_subnets:
                for attempt in range(3):
                    for subnet in config.subnets:
                        if subnet.name in fw.lan_subnets:
                            base = subnet.network.rsplit(".", 1)[0]
                            candidate = f"{base}.254"
                            if check_port(candidate, 443, timeout=3) or check_port(candidate, 22, timeout=3):
                                fw_lan_ip = candidate
                                break
                    if fw_lan_ip:
                        break
                    if attempt < 2:
                        print(f"{indent}LAN not ready, retrying in 15s...")
                        _time.sleep(15)

            if fw_lan_ip:
                lan_ports = scan_common_ports(fw_lan_ip)
                if 443 in lan_ports or 80 in lan_ports:
                    proto = "https" if 443 in lan_ports else "http"
                    print(f"{indent}Web GUI: {proto}://{fw_lan_ip}  (admin / pfsense)")
                if 22 in lan_ports:
                    print(f"{indent}SSH: ssh admin@{fw_lan_ip}  (admin / pfsense)")
                vm_ips[fw_name + "_LAN"] = fw_lan_ip
            else:
                print(f"{indent}LAN interface not detected.")
                print(f"{indent}Open pfSense console in VirtualBox to check config.")

    return vm_ips


def ssh_menu(config, vm_ips=None):
    """Offer interactive SSH access to running VMs."""
    header("SSH TO VMs")

    # Discover IPs if not provided
    if vm_ips is None:
        vm_ips = discover_vm_ips(config)

    # Detect pfSense LAN IP for each firewall if not already in vm_ips
    for fw in config.firewalls:
        if fw.vm_name + "_LAN" not in vm_ips and fw.lan_subnets:
            import time as _time
            for attempt in range(3):
                found = False
                for subnet in config.subnets:
                    if subnet.name in fw.lan_subnets:
                        base = subnet.network.rsplit(".", 1)[0]
                        candidate = f"{base}.254"
                        if check_port(candidate, 443, timeout=3) or check_port(candidate, 22, timeout=3):
                            vm_ips[fw.vm_name + "_LAN"] = candidate
                            found = True
                            break
                if found:
                    break
                if attempt < 2:
                    print(f"  {fw.vm_name} LAN not ready, retrying in 15s...")
                    _time.sleep(15)

    # Build role lookup
    vm_roles = {vm.name: vm.role for vm in config.vms}

    # Find running VMs and check SSH availability
    running = []
    for vm in config.vms:
        state = vm_manager.get_vm_state(vm.name)
        if state == "running":
            ip = vm_ips.get(vm.name)
            # For firewall VMs, prefer the LAN IP (SSH/web only accessible on LAN)
            lan_ip = vm_ips.get(vm.name + "_LAN") if vm.role == "firewall" else None
            running.append((vm.name, ip, vm.role, lan_ip))

    if not running:
        print("  No VMs currently running.")
        return

    print(f"  {len(running)} VM(s) running:\n")
    labels = []
    for name, ip, role, lan_ip in running:
        if role == "firewall" and lan_ip:
            # Firewall: check LAN IP for SSH and web access
            ssh_ok = check_port(lan_ip, 22, timeout=2)
            if ssh_ok:
                labels.append(f"{name}  (LAN: {lan_ip})  [SSH ready]")
            else:
                has_web = check_port(lan_ip, 443, timeout=2) or check_port(lan_ip, 80, timeout=2)
                if has_web:
                    proto = "https" if check_port(lan_ip, 443, timeout=2) else "http"
                    labels.append(f"{name}  (LAN: {lan_ip})  [Web GUI: {proto}://{lan_ip}]")
                else:
                    labels.append(f"{name}  (LAN: {lan_ip})  [Use VirtualBox console]")
        elif not ip:
            labels.append(f"{name}  (IP not detected)")
        else:
            ssh_ok = check_port(ip, 22, timeout=2)
            if ssh_ok:
                labels.append(f"{name}  ({ip})  [SSH ready]")
            elif role == "firewall":
                has_web = check_port(ip, 443, timeout=2) or check_port(ip, 80, timeout=2)
                if has_web:
                    proto = "https" if check_port(ip, 443, timeout=2) else "http"
                    labels.append(f"{name}  ({ip})  [No SSH — use web GUI: {proto}://{ip}]")
                else:
                    labels.append(f"{name}  ({ip})  [No SSH — use VirtualBox console]")
            else:
                labels.append(f"{name}  ({ip})  [SSH not running]")
    labels.append("Back to menu")

    idx = prompt_choice("Which VM to connect to?", labels)

    if idx == len(labels) - 1:  # Back
        return

    vm_name, detected_ip, role, lan_ip = running[idx]

    # For firewall VMs, prefer the LAN IP
    connect_ip = lan_ip if (role == "firewall" and lan_ip) else detected_ip

    # Get connection details
    if connect_ip:
        if role == "firewall" and lan_ip:
            print(f"\n  pfSense LAN IP: {lan_ip}")
            print(f"  (SSH and web GUI are only accessible on the LAN side)")
        else:
            print(f"\n  Detected IP: {connect_ip}")

        # Check SSH availability and suggest alternatives
        ssh_available = check_port(connect_ip, 22, timeout=2)
        if not ssh_available:
            print(f"  SSH (port 22) is not open on this VM.")

            # Check for web GUI
            if check_port(connect_ip, 443, timeout=2):
                print(f"  Web GUI available: https://{connect_ip}")
                if role == "firewall":
                    print(f"  Default login: admin / pfsense")
            elif check_port(connect_ip, 80, timeout=2):
                print(f"  Web GUI available: http://{connect_ip}")
                if role == "firewall":
                    print(f"  Default login: admin / pfsense")

            # Check FTP
            if check_port(connect_ip, 21, timeout=2):
                print(f"  FTP (port 21) is open — connect with: ftp {connect_ip}")

            print(f"  You can also use the VirtualBox GUI console for direct access.")
            if not prompt_yn("Try SSH anyway?", "n"):
                if prompt_yn("SSH into another VM?", "n"):
                    ssh_menu(config, vm_ips)
                return

        host = prompt("  Host/IP", connect_ip)
    else:
        print("\n  Could not detect IP for this VM.")
        print("  Enter the VM's IP address manually.")
        host = prompt("  Host/IP")
        if not host:
            print("  No IP provided, aborting.")
            return

    port = prompt_int("  SSH port", 1, 65535, 22)
    default_user = "admin" if role == "firewall" else None
    if default_user:
        username = prompt("  Username", default_user)
    else:
        username = prompt("  Username")
    if not username:
        print("  No username provided, aborting.")
        return

    section(f"Connecting to {vm_name} ({host})")

    # Try system ssh command first (best interactive experience)
    use_system_ssh = True
    try:
        subprocess.run(["ssh", "-V"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        use_system_ssh = False

    if use_system_ssh:
        print(f"  Opening SSH session to {username}@{host}:{port}...")
        print("  (Type 'exit' to return to the menu)\n")
        subprocess.run(["ssh",
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null",
                        "-o", "HostKeyAlgorithms=+ssh-rsa,ssh-dss",
                        "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
                        "-p", str(port), f"{username}@{host}"])
    else:
        # Fall back to paramiko interactive session
        password = prompt("  Password")
        ssh = SSHManager()
        if ssh.connect(host, username, password, port=port):
            print("  Connected! Enter commands (type 'exit' to quit):\n")
            while True:
                try:
                    cmd = input(f"  {username}@{vm_name}$ ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if cmd.strip().lower() in ("exit", "quit"):
                    break
                output = ssh.run_command(host, cmd)
                if output:
                    print(output)
            ssh.disconnect(host)

    print(f"\n  SSH session to {vm_name} ended.")

    # Offer to connect to another VM
    if prompt_yn("SSH into another VM?", "n"):
        ssh_menu(config, vm_ips)


def post_deploy_menu(config):
    """After deployment, offer connectivity test then SSH."""
    vm_ips = None
    if prompt_yn("Test connectivity between VMs?", "y"):
        vm_ips = connectivity_test(config)
    if prompt_yn("SSH into a VM?", "n"):
        ssh_menu(config, vm_ips)
    return vm_ips


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    vbox.check_vbox()
    clear()
    header("NETWORK SIMULATION ORCHESTRATOR")

    img_mgr = None  # Lazy-loaded for custom mode only

    # Main menu loop
    current_config = None

    while True:
        section("Main Menu")
        print("    1. Prebuilt Mode  (pick a scenario, zero config)")
        print("    2. Custom Mode    (build your own network layout)")
        print("    3. Load saved config")
        print("    4. Show VM status")
        print("    5. SSH into a VM")
        print("    6. Stop VMs")
        print("    7. Delete VMs")
        print("    8. Quit")

        choice = prompt_int("Choose", 1, 8)

        if choice == 1:
            current_config = run_prebuilt()
            if current_config is None:
                continue
            review_config(current_config)
            print("\n  Deploying scenario...")
            headless = prompt_yn("Headless mode? (y=no GUI windows)", "n")
            deployer.deploy_lab(current_config, headless=headless)
            deployer.show_lab_status(current_config)
            vm_ips = post_deploy_menu(current_config)

        elif choice == 2:
            # Lazy-load image manager for custom mode
            if img_mgr is None:
                img_mgr = ImageManager()
                section("Image Scan")
                base_dir = os.path.dirname(os.path.abspath(__file__))
                print(f"  Scanning: {base_dir}")
                if not img_mgr.scan(base_dir):
                    print("  No images found. Add .ova or .vbox files.")
                    continue
                img_mgr.display()
                img_mgr.classify_new()
                if prompt_yn("Re-classify any images?", "n"):
                    img_mgr.reclassify()

            current_config = run_custom(img_mgr)
            review_config(current_config)
            if prompt_yn("Save this config?", "y"):
                config_store.save_lab_config(current_config)
            if prompt_yn("Deploy now?", "y"):
                headless = prompt_yn("Headless mode?", "n")
                deployer.deploy_lab(current_config, headless=headless)
                deployer.show_lab_status(current_config)
                vm_ips = post_deploy_menu(current_config)

        elif choice == 3:
            path = prompt("Config file path", "configs/lab_config.json")
            current_config = config_store.load_lab_config(path)
            if current_config:
                review_config(current_config)
                if prompt_yn("Deploy this config?", "y"):
                    headless = prompt_yn("Headless mode?", "n")
                    deployer.deploy_lab(current_config, headless=headless)
                    deployer.show_lab_status(current_config)
                    vm_ips = post_deploy_menu(current_config)

        elif choice == 4:
            deployer.show_lab_status(current_config)

        elif choice == 5:
            if current_config:
                ssh_menu(current_config)
            else:
                print("  No lab config loaded. Deploy a lab first or load a config.")

        elif choice == 6:
            stop_menu()

        elif choice == 7:
            delete_menu()

        elif choice == 8:
            print("  Bye.")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
    except Exception as e:
        log.error(f"Fatal: {e}")
        import traceback
        traceback.print_exc()
