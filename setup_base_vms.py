#!/usr/bin/env python3
"""
One-time setup helper for base VMs.

This script helps configure the base VMs so that prebuilt scenarios
work correctly. Run this ONCE before using prebuilt mode.

What it does:
  1. Checks which base VMs need setup
  2. Gives you step-by-step instructions for each VM
  3. Offers to re-export OVAs after setup

After running this, your prebuilt scenarios will have:
  - SSH enabled on endpoint VMs
  - pfSense with interfaces assigned and SSH enabled
"""

import os
import sys
import time
import subprocess
import socket

import vbox
import vm_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def check_port(ip, port, timeout=3):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def header(text):
    print()
    print("=" * 70)
    print(f"  {text}".center(70))
    print("=" * 70)


def section(text):
    print(f"\n--- {text} " + "-" * max(0, 66 - len(text)))


def wait_for_input(msg="Press Enter to continue..."):
    input(f"\n  {msg}")


def setup_vsftpd_vm():
    """Guide user through enabling SSH on the vsftpd VM."""
    vm_name = "emyers_vm"

    header("SETUP: vsftpd VM (emyers_vm)")

    if not vm_manager.vm_exists(vm_name):
        print(f"  VM '{vm_name}' not found. Skipping.")
        return False

    state = vm_manager.get_vm_state(vm_name)
    print(f"  Current state: {state}")

    # Make sure it has NAT for internet access (needed to install SSH)
    print("\n  Setting NIC1 to NAT for internet access...")
    if state == "running":
        vm_manager.stop_vm(vm_name, force=True)
        time.sleep(3)

    vbox.run(["modifyvm", vm_name, "--nic1", "nat"])
    print("  [OK] NIC1 set to NAT")

    print("\n  Starting VM in GUI mode...")
    vm_manager.start_vm(vm_name, headless=False)

    section("Manual Steps Required")
    print("""
  The VM should now be booting in a VirtualBox window.
  Once it's at a login prompt, do the following:

  1. Log in to the VM console
     (Try: user=root, or check VulnHub page for credentials)

  2. Check if SSH is installed:
     $ which sshd

  3. If SSH is NOT installed, install it:
     $ apt-get update && apt-get install -y openssh-server

  4. If SSH IS installed but not running, start it:
     $ service ssh start

  5. Make SSH start on boot:
     $ update-rc.d ssh enable
     or: $ systemctl enable ssh

  6. Verify SSH is listening:
     $ netstat -tlnp | grep 22

  7. Done! Leave the VM running.
""")

    wait_for_input("Complete the steps above, then press Enter...")

    # Verify SSH
    print("  Checking if SSH is now accessible...")
    # Get VM IP from NAT (usually 10.0.2.15 but not reachable from host)
    # We need port forwarding for NAT
    print("  Setting up port forward for verification...")
    vbox.run(["controlvm", vm_name, "natpf1", "ssh,tcp,,2222,,22"], check=False)
    time.sleep(2)

    if check_port("127.0.0.1", 2222, timeout=5):
        print("  [OK] SSH is running!")
    else:
        print("  [WARN] Could not verify SSH. It may still be working.")
        print("         Check inside the VM that sshd is running.")

    # Remove port forward
    vbox.run(["controlvm", vm_name, "natpf1", "delete", "ssh"], check=False)

    # Shut down and reset NIC
    section("Finalizing")
    print("  Shutting down VM...")
    vm_manager.stop_vm(vm_name, force=False)
    time.sleep(5)
    # Force if still running
    state = vm_manager.get_vm_state(vm_name)
    if state == "running":
        vm_manager.stop_vm(vm_name, force=True)
        time.sleep(3)

    # Reset NIC back to none (deployer will configure it)
    vbox.run(["modifyvm", vm_name, "--nic1", "none"])

    # Re-export OVA
    section("Re-export OVA")
    ova_path = os.path.join(BASE_DIR, "CVE-2011-2523 (vsftpd)", "emyers_unbuntu_vsftpd.ova")
    backup = ova_path + ".bak"

    if os.path.exists(ova_path):
        print(f"  Backing up old OVA...")
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(ova_path, backup)

    print(f"  Exporting '{vm_name}' to OVA...")
    result = vbox.run(["export", vm_name, "-o", ova_path, "--ovf20"])
    if result is not None:
        size = os.path.getsize(ova_path)
        print(f"  [OK] Exported: {ova_path} ({size // 1048576} MB)")
        if os.path.exists(backup):
            os.remove(backup)
        return True
    else:
        print("  [ERROR] Export failed.")
        if os.path.exists(backup):
            os.rename(backup, ova_path)
        return False


def setup_pfsense_vm():
    """Guide user through configuring pfSense interfaces and SSH."""
    vm_name = "pfSense"

    header("SETUP: pfSense VM")

    if not vm_manager.vm_exists(vm_name):
        print(f"  VM '{vm_name}' not found. Skipping.")
        return False

    state = vm_manager.get_vm_state(vm_name)
    print(f"  Current state: {state}")

    # Set up with 2 host-only adapters so we can configure WAN/LAN
    if state == "running":
        vm_manager.stop_vm(vm_name, force=True)
        time.sleep(3)

    # Remove any installer ISO
    vm_manager.remove_ide_iso(vm_name)

    # Set NIC1=host-only (WAN), NIC2=host-only (LAN)
    # Use existing adapters
    print("\n  Configuring NICs for setup...")
    vbox.run(["modifyvm", vm_name, "--nic1=hostonly",
              "--host-only-adapter1=VirtualBox Host-Only Ethernet Adapter #3"])
    vbox.run(["modifyvm", vm_name, "--nic2=hostonly",
              "--host-only-adapter2=VirtualBox Host-Only Ethernet Adapter #4"])
    print("  NIC1 (WAN) -> Adapter #3 (192.168.30.x)")
    print("  NIC2 (LAN) -> Adapter #4 (192.168.40.x)")

    print("\n  Starting pfSense in GUI mode...")
    vm_manager.start_vm(vm_name, headless=False)

    section("Manual Steps Required")
    print("""
  The pfSense VM should now be booting.
  Once you see the pfSense menu, follow these steps:

  STEP 1 — Assign Interfaces (option 1 in pfSense menu)
    - Do you want to set up VLANs? -> n
    - Enter WAN interface name: em0
    - Enter LAN interface name: em1
    - Confirm: y

  STEP 2 — Set Interface IPs (option 2 in pfSense menu)
    Select WAN (1):
      - Configure via DHCP? -> y
      (It will get an IP from 192.168.30.x range)

    Select LAN (2):
      - Configure via DHCP? -> n
      - Enter LAN IP: 192.168.40.1
      - Subnet bit count: 24
      - Upstream gateway: (press Enter for none)
      - Enable DHCP on LAN? -> n
      - Revert to HTTP? -> n

  STEP 3 — Enable SSH (option 14 in pfSense menu)
    - Select: Enable Secure Shell (sshd)
    - It should say "sshd enabled"

  STEP 4 — Allow WAN ping (do this from web GUI)
    - Open browser: https://192.168.30.x (the WAN IP shown on console)
    - Login: admin / pfsense
    - Go to: Firewall -> Rules -> WAN
    - Add rule: Allow ICMP (any) from any to any
    - Save and Apply

  After completing all steps, leave the VM running.
""")

    wait_for_input("Complete the steps above, then press Enter...")

    # Try to verify
    print("  Checking pfSense accessibility...")
    # Check WAN side
    for ip_suffix in range(100, 201):
        ip = f"192.168.30.{ip_suffix}"
        if check_port(ip, 443, timeout=1) or check_port(ip, 80, timeout=1):
            print(f"  [OK] pfSense web GUI found at {ip}")
            if check_port(ip, 22, timeout=2):
                print(f"  [OK] SSH is enabled")
            else:
                print(f"  [WARN] SSH not detected — enable via option 14")
            break
    else:
        # Check the .1 gateway IP too
        if check_port("192.168.40.1", 443, timeout=2):
            print(f"  [OK] pfSense LAN interface at 192.168.40.1")
        else:
            print("  [WARN] Could not auto-detect pfSense. Check the console.")

    # Shut down and export
    section("Finalizing")
    wait_for_input("Ready to shut down and export? Press Enter...")

    print("  Shutting down pfSense...")
    vm_manager.stop_vm(vm_name, force=False)
    time.sleep(8)
    state = vm_manager.get_vm_state(vm_name)
    if state == "running":
        vm_manager.stop_vm(vm_name, force=True)
        time.sleep(3)

    # Reset NICs to none
    vbox.run(["modifyvm", vm_name, "--nic1", "none"])
    vbox.run(["modifyvm", vm_name, "--nic2", "none"])

    # Re-export OVA
    section("Re-export OVA")
    ova_path = os.path.join(BASE_DIR, "pfSense_export.ova")
    backup = ova_path + ".bak"

    if os.path.exists(ova_path):
        print(f"  Backing up old OVA...")
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(ova_path, backup)

    print(f"  Exporting '{vm_name}' to OVA...")
    result = vbox.run(["export", vm_name, "-o", ova_path, "--ovf20"])
    if result is not None:
        size = os.path.getsize(ova_path)
        print(f"  [OK] Exported: {ova_path} ({size // 1048576} MB)")
        if os.path.exists(backup):
            os.remove(backup)
        return True
    else:
        print("  [ERROR] Export failed.")
        if os.path.exists(backup):
            os.rename(backup, ova_path)
        return False


def main():
    vbox.check_vbox()

    header("BASE VM SETUP")
    print("""
  This script configures your base VMs for prebuilt scenarios.
  You only need to run this ONCE.

  It will:
    1. Enable SSH on the vsftpd endpoint VM
    2. Configure pfSense interfaces, SSH, and firewall rules
    3. Re-export both as OVAs

  You'll need to interact with each VM through the VirtualBox GUI
  window that opens. The script will guide you step by step.
""")

    input("  Press Enter to begin...")

    # Setup vsftpd VM
    section("VM 1 of 2: vsftpd Endpoint")
    if input("  Set up vsftpd VM? (y/n) [y]: ").strip().lower() != "n":
        setup_vsftpd_vm()
    else:
        print("  Skipped.")

    # Setup pfSense VM
    section("VM 2 of 2: pfSense Firewall")
    if input("  Set up pfSense VM? (y/n) [y]: ").strip().lower() != "n":
        setup_pfsense_vm()
    else:
        print("  Skipped.")

    header("SETUP COMPLETE")
    print("""
  Your base VMs are now configured. You can run prebuilt scenarios
  with: python cli.py -> Prebuilt Mode

  The exported OVAs now include SSH and pfSense configuration,
  so every new instance created from them will have these settings.
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
    except Exception as e:
        import traceback
        traceback.print_exc()
