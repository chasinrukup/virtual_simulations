#!/usr/bin/env python3
"""
VM Network Deployment Controller - Interactive CLI
Build VM -> Firewall (pfSense) -> VM topologies using VirtualBox.

Workflow:
  1. Scan for available ISOs
  2. Create VMs with custom configs (RAM, disk, CPUs)
  3. Attach ISOs
  4. Configure internal networks
  5. Deploy and start
"""

import os
import sys
import json
import glob
from vm_controller import VMController
from ssh_manager import SSHManager

# ── OS type mapping for VBoxManage ──────────────────────────────────────────
OS_TYPES = {
    "debian":   "Debian_64",
    "ubuntu":   "Ubuntu_64",
    "pfsense":  "FreeBSD_64",
    "netgate":  "FreeBSD_64",
    "freebsd":  "FreeBSD_64",
    "centos":   "RedHat_64",
    "kali":     "Debian_64",
    "windows":  "Windows10_64",
    "other":    "Other_64",
}


ISO_DIR = os.path.dirname(os.path.abspath(__file__))
ISO_ROLES_FILE = os.path.join(ISO_DIR, "iso_roles.json")


# ── Helpers ─────────────────────────────────────────────────────────────────
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
    """Prompt with optional default."""
    if default is not None:
        val = input(f"  {msg} [{default}]: ").strip()
        return val if val else str(default)
    return input(f"  {msg}: ").strip()


def prompt_int(msg, lo, hi, default=None):
    """Prompt for an integer in range."""
    while True:
        raw = prompt(msg, default)
        try:
            n = int(raw)
            if lo <= n <= hi:
                return n
            print(f"    Please enter a number between {lo} and {hi}.")
        except ValueError:
            print("    Invalid number.")


def prompt_choice(msg, options):
    """Prompt user to pick from a numbered list. Returns index."""
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    return prompt_int(msg, 1, len(options)) - 1


def guess_ostype(iso_name):
    """Guess VBox OS type from ISO filename."""
    name = iso_name.lower()
    for key, ostype in OS_TYPES.items():
        if key in name:
            return ostype
    return "Other_64"


# ── ISO Role Persistence ────────────────────────────────────────────────────
def load_iso_roles():
    """Load saved ISO role classifications from disk."""
    if os.path.exists(ISO_ROLES_FILE):
        with open(ISO_ROLES_FILE, "r") as f:
            return json.load(f)
    return {}


def save_iso_roles(roles):
    """Save ISO role classifications to disk."""
    with open(ISO_ROLES_FILE, "w") as f:
        json.dump(roles, f, indent=2)


# ── ISO Scanner ─────────────────────────────────────────────────────────────
def scan_isos(directory):
    """Find all .iso files in a directory."""
    isos = []
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith(".iso"):
            isos.append({
                "filename": f,
                "path": os.path.join(directory, f),
                "size_mb": round(os.path.getsize(os.path.join(directory, f)) / 1048576),
                "ostype": guess_ostype(f),
                "role": None,  # will be set by user: "endpoint" or "firewall"
            })
    return isos


# ── Main CLI Class ──────────────────────────────────────────────────────────
class NetworkBuilder:
    def __init__(self):
        self.controller = VMController()
        self.ssh = SSHManager()
        self.isos = []
        self.used_isos = set()  # filenames of ISOs already assigned to a VM
        self.vms = []           # list of VM configs the user builds
        self.networks = []      # internal network names
        self.topology = []      # connections: vm -> net

    # ─────────────────────────────────────────────── Step 0: find ISOs
    def step_scan_isos(self):
        header("STEP 0 : Locate ISOs")

        print(f"\n  Default directory: {ISO_DIR}")
        custom = prompt("Scan this directory? (y/n)", "y")
        if custom.lower() in ("n", "no"):
            iso_dir = prompt("Enter path to ISO directory")
        else:
            iso_dir = ISO_DIR

        if not os.path.isdir(iso_dir):
            print(f"  [ERROR] Directory not found: {iso_dir}")
            return False

        self.isos = scan_isos(iso_dir)
        if not self.isos:
            print("  [ERROR] No .iso files found.")
            return False

        # Load previously saved roles
        saved_roles = load_iso_roles()
        new_isos = []

        for iso in self.isos:
            if iso["filename"] in saved_roles:
                iso["role"] = saved_roles[iso["filename"]]
            else:
                new_isos.append(iso)

        section("Available ISOs")
        for i, iso in enumerate(self.isos, 1):
            role_tag = f"  [{iso['role']}]" if iso["role"] else "  [unclassified]"
            print(f"    {i}. {iso['filename']}  ({iso['size_mb']} MB){role_tag}")

        print(f"\n  Found {len(self.isos)} ISO(s).")

        # Only ask about ISOs we haven't seen before
        if new_isos:
            section("Classify new ISOs")
            print("  These ISOs haven't been classified yet.")
            print("  Tag each as 'endpoint' or 'firewall'. This is saved so")
            print("  you won't be asked again.\n")
            roles = ["endpoint", "firewall"]
            for iso in new_isos:
                print(f"  {iso['filename']}:")
                idx = prompt_choice("  Role", roles)
                iso["role"] = roles[idx]
                saved_roles[iso["filename"]] = iso["role"]

            # Save updated roles
            save_iso_roles(saved_roles)
            print("\n  Roles saved to iso_roles.json")
        else:
            print("  All ISOs already classified.")

        # Let user re-classify if they want
        reclass = prompt("Re-classify any ISOs? (y/n)", "n")
        if reclass.lower() in ("y", "yes"):
            roles = ["endpoint", "firewall"]
            iso_labels = [f"{iso['filename']}  (currently: {iso['role']})"
                          for iso in self.isos]
            while True:
                print()
                idx = prompt_choice("  Which ISO to re-classify?", iso_labels)
                print(f"  {self.isos[idx]['filename']}:")
                role_idx = prompt_choice("  New role", roles)
                self.isos[idx]["role"] = roles[role_idx]
                saved_roles[self.isos[idx]["filename"]] = roles[role_idx]
                iso_labels[idx] = (f"{self.isos[idx]['filename']}  "
                                   f"(currently: {roles[role_idx]})")
                if prompt("Re-classify another? (y/n)", "n").lower() not in ("y", "yes"):
                    break
            save_iso_roles(saved_roles)

        # Summary
        fw_count = sum(1 for iso in self.isos if iso["role"] == "firewall")
        ep_count = sum(1 for iso in self.isos if iso["role"] == "endpoint")
        print(f"\n  Endpoints: {ep_count}  |  Firewalls: {fw_count}")
        return True

    # ─────────────────────────────────────────────── Step 1: create VMs
    def step_create_vms(self):
        header("STEP 1 : Create Virtual Machines")

        num = prompt_int("How many VMs do you want to create?", 1, 20, 2)

        for idx in range(num):
            section(f"VM {idx + 1} of {num}")
            print("  What role is this VM?")
            role_idx = prompt_choice("  Role", ["endpoint", "firewall"])
            role = ["endpoint", "firewall"][role_idx]
            vm = self._configure_one_vm(idx + 1, role)
            self.vms.append(vm)
            print(f"\n  [OK] VM configured: {vm['name']} ({role})")

        # Summary
        section("VM Summary")
        for vm in self.vms:
            iso_name = os.path.basename(vm["iso"]) if vm["iso"] else "none"
            print(f"    {vm['name']:20s}  RAM={vm['ram_mb']}MB  "
                  f"CPUs={vm['cpus']}  Disk={vm['disk_mb']}MB  "
                  f"ISO={iso_name}")

    def _configure_one_vm(self, default_num, role="endpoint"):
        """Interactively configure a single VM."""
        name = prompt("VM name", f"VM{default_num}")

        # Filter ISOs by role AND exclude already-used ones
        filtered = [iso for iso in self.isos
                    if iso["role"] == role
                    and iso["filename"] not in self.used_isos]
        if not filtered:
            print(f"  [WARN] No available ISOs classified as '{role}'. Showing all unused ISOs.")
            filtered = [iso for iso in self.isos
                        if iso["filename"] not in self.used_isos]

        if not filtered:
            print("  [WARN] All ISOs are already in use. Showing all ISOs.")
            filtered = [iso for iso in self.isos if iso["role"] == role]

        # Pick ISO
        print(f"\n  Select an ISO to mount ({role} ISOs):")
        iso_labels = [f"{iso['filename']}  ({iso['size_mb']} MB)"
                      for iso in filtered]
        iso_labels.append("(none - no ISO)")
        choice = prompt_choice("ISO number", iso_labels)
        if choice < len(filtered):
            iso_path = filtered[choice]["path"]
            ostype = filtered[choice]["ostype"]
            self.used_isos.add(filtered[choice]["filename"])
        else:
            iso_path = None
            ostype = "Other_64"

        # Override OS type?
        print(f"\n  Detected OS type: {ostype}")
        print("  Available OS types:")
        types_list = list(OS_TYPES.items())
        for i, (key, val) in enumerate(types_list, 1):
            print(f"    {i}. {key:10s} -> {val}")
        override = prompt("Keep detected type? (y/n)", "y")
        if override.lower() in ("n", "no"):
            oi = prompt_int("Pick OS type number", 1, len(types_list))
            ostype = types_list[oi - 1][1]

        # Hardware
        ram = prompt_int("RAM in MB", 256, 65536, 2048)
        cpus = prompt_int("Number of CPUs", 1, 16, 2)
        disk = prompt_int("Disk size in MB", 5000, 500000, 20000)

        return {
            "name": name,
            "iso": iso_path,
            "ostype": ostype,
            "ram_mb": ram,
            "cpus": cpus,
            "disk_mb": disk,
        }

    # ─────────────────────────────────────────────── Step 2: networks
    def step_configure_networks(self):
        header("STEP 2 : Configure Networks")

        print("""
  Network modes available:
    intnet   - Internal network (VMs talk to each other, isolated)
    nat      - NAT (VM can reach internet, no inbound)
    hostonly - Host-only (VM <-> Host only)
    bridged  - Bridged (VM on your physical LAN)

  For a VM -> pfSense -> VM topology, use internal networks:
    - Create one intnet for the WAN side (e.g., "wan_net")
    - Create one intnet for the LAN side (e.g., "lan_net")
    - Attach pfSense to both
    - Attach each endpoint VM to one side
""")

        num_nets = prompt_int("How many internal networks to create?", 1, 10, 2)

        for i in range(num_nets):
            name = prompt(f"  Name for network {i + 1}", f"intnet{i + 1}")
            self.networks.append(name)

        section("Defined Networks")
        for net in self.networks:
            print(f"    - {net}")

        # Assign adapters
        section("Assign Network Adapters to VMs")

        for vm in self.vms:
            print(f"\n  VM: {vm['name']}")
            num_adapters = prompt_int(
                f"How many network adapters for '{vm['name']}'?", 1, 4, 1
            )
            vm["adapters"] = []

            for a in range(num_adapters):
                print(f"\n    Adapter {a + 1}:")
                modes = ["intnet", "nat", "hostonly", "bridged"]
                mode_idx = prompt_choice("    Network mode", modes)
                mode = modes[mode_idx]

                net_name = None
                if mode == "intnet":
                    print("    Available internal networks:")
                    net_idx = prompt_choice("    Pick network", self.networks)
                    net_name = self.networks[net_idx]
                elif mode == "hostonly":
                    net_name = prompt("    Host-only adapter name",
                                      "VirtualBox Host-Only Ethernet Adapter")
                elif mode == "bridged":
                    net_name = prompt("    Bridged to (physical adapter name)", "")

                vm["adapters"].append({
                    "num": a + 1,
                    "mode": mode,
                    "net_name": net_name,
                })
                status = f"{mode}" + (f" ({net_name})" if net_name else "")
                print(f"    -> Adapter {a + 1}: {status}")

    # ─────────────────────────────────────────────── Step 3: review
    def step_review(self):
        header("STEP 3 : Review Topology")

        section("Virtual Machines")
        for vm in self.vms:
            iso_name = os.path.basename(vm["iso"]) if vm["iso"] else "(none)"
            print(f"\n    [{vm['name']}]")
            print(f"      OS type : {vm['ostype']}")
            print(f"      RAM     : {vm['ram_mb']} MB")
            print(f"      CPUs    : {vm['cpus']}")
            print(f"      Disk    : {vm['disk_mb']} MB")
            print(f"      ISO     : {iso_name}")
            for adp in vm.get("adapters", []):
                net = adp.get("net_name", "")
                print(f"      NIC {adp['num']}   : {adp['mode']}"
                      + (f" -> {net}" if net else ""))

        section("Networks")
        for net in self.networks:
            members = [vm["name"] for vm in self.vms
                       for a in vm.get("adapters", [])
                       if a.get("net_name") == net]
            print(f"    {net}: {', '.join(members) if members else '(no VMs)'}")

        # ASCII topology
        self._draw_topology()

    def _draw_topology(self):
        """Draw a simple ASCII topology diagram."""
        section("Topology Diagram")

        # Find firewall VMs (connected to 2+ networks)
        fw_vms = [vm for vm in self.vms
                  if len([a for a in vm.get("adapters", [])
                          if a["mode"] == "intnet"]) >= 2]
        endpoint_vms = [vm for vm in self.vms if vm not in fw_vms]

        if not fw_vms:
            print("    (No multi-homed firewall detected)")
            for vm in self.vms:
                nets = [a.get("net_name", a["mode"])
                        for a in vm.get("adapters", [])]
                print(f"    [{vm['name']}] -- {', '.join(nets)}")
            return

        for fw in fw_vms:
            intnet_adapters = [a for a in fw.get("adapters", [])
                               if a["mode"] == "intnet"]
            if len(intnet_adapters) < 2:
                continue

            wan_net = intnet_adapters[0]["net_name"]
            lan_net = intnet_adapters[1]["net_name"]

            wan_vms = [vm["name"] for vm in endpoint_vms
                       for a in vm.get("adapters", [])
                       if a.get("net_name") == wan_net]
            lan_vms = [vm["name"] for vm in endpoint_vms
                       for a in vm.get("adapters", [])
                       if a.get("net_name") == lan_net]

            print()
            for wv in wan_vms:
                print(f"    [{wv}]")
                print(f"        |")
            print(f"        | ({wan_net})")
            print(f"        |")
            print(f"    [{fw['name']}]")
            print(f"        |")
            print(f"        | ({lan_net})")
            print(f"        |")
            for lv in lan_vms:
                print(f"    [{lv}]")

    # ─────────────────────────────────────────────── Step 4: deploy
    def step_deploy(self):
        header("STEP 4 : Deploy")

        go = prompt("Deploy this configuration to VirtualBox? (y/n)", "y")
        if go.lower() not in ("y", "yes"):
            print("  Deployment cancelled.")
            return False

        total = len(self.vms)
        for i, vm in enumerate(self.vms, 1):
            section(f"[{i}/{total}] Deploying {vm['name']}")

            # Create VM
            ok = self.controller.create_vm(
                name=vm["name"],
                ostype=vm["ostype"],
                ram_mb=vm["ram_mb"],
                cpus=vm["cpus"],
                disk_size_mb=vm["disk_mb"],
            )
            if not ok:
                print(f"  [FAIL] Could not create {vm['name']}")
                continue

            # Attach ISO
            if vm["iso"]:
                self.controller.attach_iso(vm["name"], vm["iso"])

            # Configure network adapters
            for adp in vm.get("adapters", []):
                self.controller.configure_adapter(
                    vm["name"],
                    adp["num"],
                    adp["mode"],
                    adp.get("net_name"),
                )

        print("\n  All VMs deployed.")
        return True

    # ─────────────────────────────────────────────── Step 5: start
    def step_start(self):
        header("STEP 5 : Start VMs")

        start = prompt("Start all VMs now? (y/n)", "y")
        if start.lower() not in ("y", "yes"):
            print("  Skipped.")
            return

        headless = prompt("Headless mode (no GUI windows)? (y/n)", "n")
        use_headless = headless.lower() in ("y", "yes")

        # Start firewalls first (multi-homed VMs)
        fw_vms = [vm for vm in self.vms
                  if len(vm.get("adapters", [])) >= 2]
        other_vms = [vm for vm in self.vms if vm not in fw_vms]

        for vm in fw_vms + other_vms:
            self.controller.start_vm(vm["name"], use_headless)

        # Show live status so user knows what's running
        self.show_status()

        if use_headless:
            print("\n  VMs are running headless (no GUI windows).")
            print("  To open a GUI window for a headless VM, use VirtualBox Manager")
            print("  or run: VBoxManage startvm <name> --type separate")

        print("\n  Next steps:")
        print("    1. Wait for VMs to boot (1-2 min)")
        print("    2. Install OS from ISO inside each VM")
        print("    3. Configure static IPs on each VM")
        print("    4. Configure firewall WAN/LAN interfaces")
        print("    5. Test connectivity: ping between VMs through firewall")

    # ─────────────────────────────────────────────── Status
    def show_status(self):
        """Show the state of all VMs we've deployed."""
        section("VM Status")

        # If we have VMs from this session, check those
        vms_to_check = self.vms if self.vms else []

        if vms_to_check:
            for vm in vms_to_check:
                state = self.controller.get_vm_state(vm["name"])
                if state == "running":
                    indicator = "[RUNNING]"
                elif state == "poweroff":
                    indicator = "[OFF]    "
                elif state == "saved":
                    indicator = "[SAVED]  "
                else:
                    indicator = f"[{state.upper()}]"
                adapters = ", ".join(
                    f"NIC{a['num']}:{a['mode']}"
                    + (f"({a['net_name']})" if a.get('net_name') else "")
                    for a in vm.get("adapters", [])
                )
                print(f"    {indicator}  {vm['name']:20s}  {adapters}")
        else:
            # Fall back to listing all VirtualBox VMs
            running = self.controller.list_running_vms()
            all_vms = self.controller.list_vms()
            print("  All registered VMs:")
            print(f"    {all_vms or '(none)'}")
            print("\n  Currently running:")
            print(f"    {running or '(none)'}")

    # ─────────────────────────────────────────────── Stop VMs
    def step_stop(self):
        header("STOP VMs")

        # Get list of running VMs from VirtualBox
        running_raw = self.controller.list_running_vms()
        if not running_raw or running_raw.strip() == "":
            print("  No VMs are currently running.")
            return

        # Parse running VM names
        running_vms = []
        for line in running_raw.splitlines():
            line = line.strip()
            if line and '"' in line:
                name = line.split('"')[1]
                running_vms.append(name)

        if not running_vms:
            print("  No VMs are currently running.")
            return

        print(f"  {len(running_vms)} VM(s) currently running:\n")
        for i, name in enumerate(running_vms, 1):
            print(f"    {i}. {name}")

        print(f"\n    {len(running_vms) + 1}. Stop ALL")
        print(f"    {len(running_vms) + 2}. Cancel")

        choice = prompt_int("Which VM to stop?", 1, len(running_vms) + 2)

        if choice == len(running_vms) + 2:
            print("  Cancelled.")
            return

        if choice == len(running_vms) + 1:
            # Stop all
            force = prompt("Force power off? (y = instant, n = graceful ACPI shutdown)", "n")
            use_force = force.lower() in ("y", "yes")
            for name in running_vms:
                print(f"  Stopping '{name}'...")
                self.controller.stop_vm(name, force=use_force)
            print(f"\n  All {len(running_vms)} VMs stopped.")
        else:
            # Stop one
            name = running_vms[choice - 1]
            force = prompt("Force power off? (y = instant, n = graceful ACPI shutdown)", "n")
            use_force = force.lower() in ("y", "yes")
            print(f"  Stopping '{name}'...")
            self.controller.stop_vm(name, force=use_force)

        # Show updated status
        self.show_status()

    # ─────────────────────────────────────────────── Delete VMs
    def step_delete(self):
        header("DELETE VMs")

        # Get all registered VMs
        all_raw = self.controller.list_vms()
        if not all_raw or all_raw.strip() == "":
            print("  No VMs registered in VirtualBox.")
            return

        all_vms = []
        for line in all_raw.splitlines():
            line = line.strip()
            if line and '"' in line:
                name = line.split('"')[1]
                state = self.controller.get_vm_state(name)
                all_vms.append((name, state))

        if not all_vms:
            print("  No VMs registered.")
            return

        print(f"  {len(all_vms)} VM(s) registered:\n")
        for i, (name, state) in enumerate(all_vms, 1):
            print(f"    {i}. {name}  [{state}]")

        print(f"\n    {len(all_vms) + 1}. Delete ALL")
        print(f"    {len(all_vms) + 2}. Cancel")

        choice = prompt_int("Which VM to delete?", 1, len(all_vms) + 2)

        if choice == len(all_vms) + 2:
            print("  Cancelled.")
            return

        if choice == len(all_vms) + 1:
            confirm = prompt(f"Delete ALL {len(all_vms)} VMs and their files? (yes/no)", "no")
            if confirm.lower() != "yes":
                print("  Cancelled.")
                return
            for name, state in all_vms:
                if state == "running":
                    print(f"  Stopping '{name}' first...")
                    self.controller.stop_vm(name, force=True)
                print(f"  Deleting '{name}'...")
                self.controller.delete_vm(name)
            print(f"\n  All {len(all_vms)} VMs deleted.")
        else:
            name, state = all_vms[choice - 1]
            confirm = prompt(f"Delete '{name}' and all its files? (yes/no)", "no")
            if confirm.lower() != "yes":
                print("  Cancelled.")
                return
            if state == "running":
                print(f"  Stopping '{name}' first...")
                self.controller.stop_vm(name, force=True)
            print(f"  Deleting '{name}'...")
            self.controller.delete_vm(name)

        self.show_status()

    # ─────────────────────────────────────────────── Save config
    def save_config(self):
        section("Save Configuration")
        save = prompt("Save this config to file? (y/n)", "y")
        if save.lower() not in ("y", "yes"):
            return

        filename = prompt("Filename", "network_config.json")
        config = {
            "vms": self.vms,
            "networks": self.networks,
        }
        with open(filename, "w") as f:
            json.dump(config, f, indent=2)
        print(f"  [OK] Saved to {filename}")

    # ─────────────────────────────────────────────── Quick deploy preset
    def quick_deploy(self):
        """Preset: VM -> pfSense -> VM with two internal networks."""
        header("QUICK DEPLOY : VM -> pfSense -> VM")

        if not self.isos:
            print("  [ERROR] No ISOs found. Run scan first.")
            return False

        print("\n  This will set up:")
        print("    [VM1] --( wan_net )-- [pfSense] --( lan_net )-- [VM2]")
        print()

        # Filter ISOs by role, excluding already-used ones
        endpoint_isos = [iso for iso in self.isos
                         if iso["role"] == "endpoint"
                         and iso["filename"] not in self.used_isos]
        firewall_isos = [iso for iso in self.isos
                         if iso["role"] == "firewall"
                         and iso["filename"] not in self.used_isos]

        if not endpoint_isos:
            print("  [ERROR] No endpoint ISOs available. Classify at least one ISO as 'endpoint'.")
            return False
        if not firewall_isos:
            print("  [ERROR] No firewall ISOs available. Classify at least one ISO as 'firewall'.")
            return False

        # VM1 — pick from endpoints
        ep_labels = [f"{iso['filename']}  ({iso['size_mb']} MB)" for iso in endpoint_isos]
        print("  Select ISO for VM1 (endpoint):")
        idx1 = prompt_choice("  ISO", ep_labels)
        picked_vm1 = endpoint_isos[idx1]
        self.used_isos.add(picked_vm1["filename"])

        # Firewall — pick from firewalls
        fw_labels = [f"{iso['filename']}  ({iso['size_mb']} MB)" for iso in firewall_isos]
        print("\n  Select ISO for firewall:")
        idx_fw = prompt_choice("  ISO", fw_labels)
        picked_fw = firewall_isos[idx_fw]
        self.used_isos.add(picked_fw["filename"])

        # VM2 — pick from remaining endpoints
        remaining_ep = [iso for iso in endpoint_isos
                        if iso["filename"] not in self.used_isos]
        if not remaining_ep:
            print("  [ERROR] No remaining endpoint ISOs for VM2.")
            return False
        ep2_labels = [f"{iso['filename']}  ({iso['size_mb']} MB)" for iso in remaining_ep]
        print("\n  Select ISO for VM2 (endpoint):")
        idx2 = prompt_choice("  ISO", ep2_labels)
        picked_vm2 = remaining_ep[idx2]
        self.used_isos.add(picked_vm2["filename"])

        # Quick hardware config
        section("Hardware (press Enter for defaults)")
        vm1_ram = prompt_int("VM1 RAM (MB)", 256, 65536, 2048)
        vm1_disk = prompt_int("VM1 Disk (MB)", 5000, 500000, 20000)
        fw_ram = prompt_int("pfSense RAM (MB)", 256, 65536, 1024)
        fw_disk = prompt_int("pfSense Disk (MB)", 5000, 500000, 10000)
        vm2_ram = prompt_int("VM2 RAM (MB)", 256, 65536, 2048)
        vm2_disk = prompt_int("VM2 Disk (MB)", 5000, 500000, 20000)

        # Build config
        self.networks = ["wan_net", "lan_net"]

        self.vms = [
            {
                "name": prompt("VM1 name", "VM1"),
                "iso": picked_vm1["path"],
                "ostype": picked_vm1["ostype"],
                "ram_mb": vm1_ram, "cpus": 2, "disk_mb": vm1_disk,
                "adapters": [{"num": 1, "mode": "intnet", "net_name": "wan_net"}],
            },
            {
                "name": prompt("Firewall name", "Firewall"),
                "iso": picked_fw["path"],
                "ostype": picked_fw["ostype"],
                "ram_mb": fw_ram, "cpus": 1, "disk_mb": fw_disk,
                "adapters": [
                    {"num": 1, "mode": "intnet", "net_name": "wan_net"},
                    {"num": 2, "mode": "intnet", "net_name": "lan_net"},
                ],
            },
            {
                "name": prompt("VM2 name", "VM2"),
                "iso": picked_vm2["path"],
                "ostype": picked_vm2["ostype"],
                "ram_mb": vm2_ram, "cpus": 2, "disk_mb": vm2_disk,
                "adapters": [{"num": 1, "mode": "intnet", "net_name": "lan_net"}],
            },
        ]

        return True

    # ─────────────────────────────────────────────── Main menu
    def run(self):
        clear()
        header("VM NETWORK DEPLOYMENT CONTROLLER")
        print("  Build VM -> Firewall -> VM topologies with VirtualBox\n")

        # Scan ISOs first
        if not self.step_scan_isos():
            return

        while True:
            section("Main Menu")
            print("    1. Quick Deploy  (VM -> Firewall -> VM preset)")
            print("    2. Custom Build  (full interactive setup)")
            print("    3. Show VM Status (running / off)")
            print("    4. Stop VMs")
            print("    5. Delete VMs")
            print("    6. Quit")

            choice = prompt_int("Choose", 1, 6)

            if choice == 1:
                if self.quick_deploy():
                    self.step_review()
                    self.save_config()
                    if self.step_deploy():
                        self.step_start()

            elif choice == 2:
                self.step_create_vms()
                self.step_configure_networks()
                self.step_review()
                self.save_config()
                if self.step_deploy():
                    self.step_start()

            elif choice == 3:
                self.show_status()

            elif choice == 4:
                self.step_stop()

            elif choice == 5:
                self.step_delete()

            elif choice == 6:
                print("  Bye.")
                break


def main():
    builder = NetworkBuilder()
    try:
        builder.run()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
