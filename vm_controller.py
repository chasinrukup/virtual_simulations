#!/usr/bin/env python3
"""
VBoxManage wrapper - creates VMs, attaches ISOs, configures networks.
"""

import subprocess
import os
import sys
import time

VBOXMANAGE = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"


def run_vbox(args, check=True):
    """Run a VBoxManage command and return stdout."""
    cmd = [VBOXMANAGE] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=check
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] VBoxManage failed: {e.stderr.strip()}")
        return None


class VMController:
    """Controls VirtualBox VMs via VBoxManage CLI."""

    def __init__(self):
        if not os.path.exists(VBOXMANAGE):
            print(f"[ERROR] VBoxManage not found at: {VBOXMANAGE}")
            sys.exit(1)

    # ------------------------------------------------------------------ info
    def list_vms(self):
        """List all registered VMs."""
        out = run_vbox(["list", "vms"])
        return out if out else ""

    def list_running_vms(self):
        """List currently running VMs."""
        out = run_vbox(["list", "runningvms"])
        return out if out else ""

    def vm_exists(self, name):
        """Check if a VM with this name already exists."""
        return f'"{name}"' in self.list_vms()

    def list_hostonlyifs(self):
        """List host-only interfaces."""
        out = run_vbox(["list", "hostonlyifs"])
        return out if out else ""

    def list_intnet(self):
        """List internal networks (parsed from VM configs)."""
        out = run_vbox(["list", "intnets"], check=False)
        return out if out else ""

    # -------------------------------------------------------------- create VM
    def create_vm(self, name, ostype="Debian_64", ram_mb=2048, cpus=2,
                  disk_size_mb=20000, vram=16):
        """Create a new VM with a virtual hard disk."""
        if self.vm_exists(name):
            print(f"  [WARN] VM '{name}' already exists, skipping creation.")
            return True

        print(f"  Creating VM: {name} (OS: {ostype}, RAM: {ram_mb}MB, "
              f"CPUs: {cpus}, Disk: {disk_size_mb}MB)")

        # Create and register
        out = run_vbox(["createvm", "--name", name, "--ostype", ostype,
                        "--register"])
        if out is None:
            return False

        # Parse the VM settings file path to find the VM folder
        vm_folder = None
        for line in out.splitlines():
            if "Settings file:" in line:
                vbox_path = line.split("'")[1] if "'" in line else ""
                vm_folder = os.path.dirname(vbox_path)
                break

        if not vm_folder:
            # Fallback: default VirtualBox VMs folder
            vm_folder = os.path.join(
                os.path.expanduser("~"), "VirtualBox VMs", name
            )

        # Configure hardware
        run_vbox(["modifyvm", name,
                  "--memory", str(ram_mb),
                  "--cpus", str(cpus),
                  "--vram", str(vram),
                  "--graphicscontroller", "vmsvga",
                  "--audio-driver", "none",
                  "--boot1", "dvd",
                  "--boot2", "disk",
                  "--boot3", "none",
                  "--boot4", "none"])

        # Create virtual hard disk
        disk_path = os.path.join(vm_folder, f"{name}.vdi")
        if not os.path.exists(disk_path):
            run_vbox(["createmedium", "disk",
                      "--filename", disk_path,
                      "--size", str(disk_size_mb),
                      "--format", "VDI"])

        # Add SATA controller and attach disk
        run_vbox(["storagectl", name,
                  "--name", "SATA",
                  "--add", "sata",
                  "--controller", "IntelAhci",
                  "--portcount", "2"])

        run_vbox(["storageattach", name,
                  "--storagectl", "SATA",
                  "--port", "0",
                  "--device", "0",
                  "--type", "hdd",
                  "--medium", disk_path])

        # Add IDE controller for DVD/ISO
        run_vbox(["storagectl", name,
                  "--name", "IDE",
                  "--add", "ide"])

        print(f"  [OK] VM '{name}' created.")
        return True

    # -------------------------------------------------------------- attach ISO
    def attach_iso(self, vm_name, iso_path):
        """Attach an ISO to the VM's IDE DVD drive."""
        if not os.path.exists(iso_path):
            print(f"  [ERROR] ISO not found: {iso_path}")
            return False

        result = run_vbox(["storageattach", vm_name,
                           "--storagectl", "IDE",
                           "--port", "0",
                           "--device", "0",
                           "--type", "dvddrive",
                           "--medium", iso_path])
        if result is not None:
            print(f"  [OK] ISO attached to '{vm_name}': {os.path.basename(iso_path)}")
            return True
        return False

    def detach_iso(self, vm_name):
        """Remove ISO from VM."""
        run_vbox(["storageattach", vm_name,
                  "--storagectl", "IDE",
                  "--port", "0",
                  "--device", "0",
                  "--type", "dvddrive",
                  "--medium", "emptydrive"])

    # --------------------------------------------------------- network config
    def configure_adapter(self, vm_name, adapter_num, mode, net_name=None):
        """
        Configure a network adapter.

        adapter_num: 1-4
        mode:        "intnet", "hostonly", "nat", "bridged", "none"
        net_name:    internal network name (for intnet) or host-only IF name
        """
        nic = str(adapter_num)

        # VBox 7.x uses --nicN=<type> --host-only-adapterN=<name> syntax
        if mode == "intnet":
            args = ["modifyvm", vm_name,
                    f"--nic{nic}=intnet",
                    f"--intnet{nic}={net_name or 'intnet'}"]
        elif mode == "hostonly":
            args = ["modifyvm", vm_name,
                    f"--nic{nic}=hostonly",
                    f"--host-only-adapter{nic}={net_name or 'VirtualBox Host-Only Ethernet Adapter'}"]
        elif mode == "nat":
            args = ["modifyvm", vm_name,
                    f"--nic{nic}=nat"]
        elif mode == "bridged":
            args = ["modifyvm", vm_name,
                    f"--nic{nic}=bridged",
                    f"--bridge-adapter{nic}={net_name or ''}"]
        elif mode == "none":
            args = ["modifyvm", vm_name,
                    f"--nic{nic}=none"]
        else:
            print(f"  [ERROR] Unknown network mode: {mode}")
            return False

        result = run_vbox(args)
        # Enable promiscuous mode for intnet/hostonly (needed for firewalls)
        if result is not None and mode in ("intnet", "hostonly"):
            run_vbox(["modifyvm", vm_name,
                      f"--nic-promisc{nic}=allow-all"])
        return result is not None

    def create_host_network(self, name, ip, netmask):
        """Create a VirtualBox host-only network."""
        out = run_vbox(["hostonlyif", "create"])
        if out and "was successfully created" in out:
            # Parse interface name from output
            for line in out.splitlines():
                if "'" in line:
                    iface = line.split("'")[1]
                    run_vbox(["hostonlyif", "ipconfig", iface,
                              "--ip", ip, "--netmask", netmask])
                    print(f"  [OK] Host-only network '{iface}' -> {ip}/{netmask}")
                    return iface
        return None

    # ----------------------------------------------------------- VM lifecycle
    def start_vm(self, name, headless=False):
        """Start a VM."""
        mode = "headless" if headless else "gui"
        print(f"  Starting '{name}' ({mode})...")
        result = run_vbox(["startvm", name, "--type", mode])
        return result is not None

    def stop_vm(self, name, force=False):
        """Stop a VM (ACPI poweroff or force poweroff)."""
        if force:
            result = run_vbox(["controlvm", name, "poweroff"])
        else:
            result = run_vbox(["controlvm", name, "acpipowerbutton"])
        return result is not None

    def delete_vm(self, name):
        """Unregister and delete a VM and all its files."""
        result = run_vbox(["unregistervm", name, "--delete"])
        return result is not None

    def get_vm_info(self, name):
        """Get detailed VM info."""
        return run_vbox(["showvminfo", name, "--machinereadable"])

    def get_vm_state(self, name):
        """Get the current state of a VM (running, poweroff, etc)."""
        info = self.get_vm_info(name)
        if info:
            for line in info.splitlines():
                if line.startswith("VMState="):
                    return line.split("=")[1].strip('"')
        return "unknown"

    # --------------------------------------------------------- import OVA
    def import_vm(self, ova_path, name=None):
        """Import an OVA appliance."""
        if not os.path.exists(ova_path):
            print(f"  [ERROR] OVA not found: {ova_path}")
            return False

        args = ["import", ova_path]
        if name:
            args.extend(["--vsys", "0", "--vmname", name])

        print(f"  Importing OVA: {os.path.basename(ova_path)}...")
        result = run_vbox(args)
        return result is not None

    def configure_vm_network(self, vm_name, adapter, mode, net_name):
        """Backward-compatible alias for configure_adapter."""
        return self.configure_adapter(vm_name, adapter, mode, net_name)
