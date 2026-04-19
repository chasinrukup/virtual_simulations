"""
VM lifecycle management - create, configure, start, stop, delete.
"""

import os
import vbox
from logger import get_logger

log = get_logger()


def vm_exists(name):
    """Check if a VM with this name is registered."""
    out = vbox.run(["list", "vms"], check=False)
    return out is not None and f'"{name}"' in out


def list_vms():
    """List all registered VMs. Returns raw VBoxManage output."""
    return vbox.run(["list", "vms"], check=False) or ""


def list_running_vms():
    """List running VMs. Returns raw VBoxManage output."""
    return vbox.run(["list", "runningvms"], check=False) or ""


def get_vm_state(name):
    """Get VM state: 'running', 'poweroff', 'saved', etc."""
    info = vbox.run(["showvminfo", name, "--machinereadable"], check=False)
    if info:
        for line in info.splitlines():
            if line.startswith("VMState="):
                return line.split("=")[1].strip('"')
    return "unknown"


def create_vm(name, ostype="Debian_64", ram_mb=2048, cpus=2,
              disk_size_mb=20000, vram=16):
    """Create a new VM with virtual hard disk."""
    if vm_exists(name):
        log.warning(f"VM '{name}' already exists, skipping creation.")
        return True

    log.info(f"Creating VM: {name} (OS: {ostype}, RAM: {ram_mb}MB, "
             f"CPUs: {cpus}, Disk: {disk_size_mb}MB)")

    # Create and register
    out = vbox.run(["createvm", "--name", name, "--ostype", ostype, "--register"])
    if out is None:
        return False

    # Find VM folder from settings file path
    vm_folder = None
    for line in out.splitlines():
        if "Settings file:" in line and "'" in line:
            vm_folder = os.path.dirname(line.split("'")[1])
            break
    if not vm_folder:
        vm_folder = os.path.join(os.path.expanduser("~"), "VirtualBox VMs", name)

    # Hardware config
    vbox.run(["modifyvm", name,
              "--memory", str(ram_mb),
              "--cpus", str(cpus),
              "--vram", str(vram),
              "--graphicscontroller", "vmsvga",
              "--audio-driver", "none",
              "--boot1", "dvd",
              "--boot2", "disk",
              "--boot3", "none",
              "--boot4", "none"])

    # Create disk
    disk_path = os.path.join(vm_folder, f"{name}.vdi")
    if not os.path.exists(disk_path):
        vbox.run(["createmedium", "disk",
                  "--filename", disk_path,
                  "--size", str(disk_size_mb),
                  "--format", "VDI"])

    # SATA controller + attach disk
    vbox.run(["storagectl", name,
              "--name", "SATA", "--add", "sata",
              "--controller", "IntelAhci", "--portcount", "2"])
    vbox.run(["storageattach", name,
              "--storagectl", "SATA", "--port", "0", "--device", "0",
              "--type", "hdd", "--medium", disk_path])

    # IDE controller for DVD/ISO
    vbox.run(["storagectl", name, "--name", "IDE", "--add", "ide"])

    # Ensure no NAT/bridged NICs remain from VBox defaults
    disable_all_nics(name)
    log.info(f"[OK] VM '{name}' created.")
    return True


def attach_iso(vm_name, iso_path):
    """Mount an ISO to the VM's DVD drive."""
    if not os.path.exists(iso_path):
        log.error(f"ISO not found: {iso_path}")
        return False

    result = vbox.run(["storageattach", vm_name,
                       "--storagectl", "IDE",
                       "--port", "0", "--device", "0",
                       "--type", "dvddrive", "--medium", iso_path])
    if result is not None:
        log.info(f"[OK] ISO mounted on '{vm_name}': {os.path.basename(iso_path)}")
        return True
    return False


def detach_iso(vm_name):
    """Remove ISO from VM."""
    vbox.run(["storageattach", vm_name,
              "--storagectl", "IDE",
              "--port", "0", "--device", "0",
              "--type", "dvddrive", "--medium", "emptydrive"])


def disable_all_nics(vm_name):
    """Set all 8 NICs to 'none' on a VM. Called before reassigning NICs
    so no leftover NAT/bridged adapters remain from the original image."""
    for nic in range(1, 9):
        vbox.run(["modifyvm", vm_name, f"--nic{nic}=none"], check=False)


def configure_nic(vm_name, adapter_num, adapter_name):
    """
    Attach a VM NIC to a host-only adapter.

    adapter_num:  1-4
    adapter_name: VBox host-only adapter name
    """
    nic = str(adapter_num)
    # VBox 7.x syntax: --nicN=hostonly --host-only-adapterN=<name>
    result = vbox.run(["modifyvm", vm_name,
                       f"--nic{nic}=hostonly",
                       f"--host-only-adapter{nic}={adapter_name}"])
    if result is not None:
        # Enable promiscuous mode (needed for firewall routing)
        vbox.run(["modifyvm", vm_name,
                  f"--nic-promisc{nic}=allow-all"])
        log.info(f"[OK] {vm_name} NIC{nic} -> {adapter_name}")
        return True
    return False


def start_vm(name, headless=False):
    """Start a VM."""
    mode = "headless" if headless else "gui"
    log.info(f"Starting '{name}' ({mode})...")
    result = vbox.run(["startvm", name, "--type", mode])
    return result is not None


def stop_vm(name, force=False):
    """Stop a VM. force=True for instant poweroff, False for ACPI shutdown."""
    action = "poweroff" if force else "acpipowerbutton"
    log.info(f"Stopping '{name}' ({action})...")
    result = vbox.run(["controlvm", name, action])
    return result is not None


def delete_vm(name, keep_files=False):
    """
    Unregister and delete a VM.
    keep_files=True just unregisters without deleting disk files
    (used for .vbox VMs where the source files must be preserved).
    """
    if keep_files:
        log.info(f"Unregistering VM '{name}' (keeping files)...")
        result = vbox.run(["unregistervm", name])
    else:
        log.info(f"Deleting VM '{name}'...")
        result = vbox.run(["unregistervm", name, "--delete"])
    return result is not None


def import_ova(ova_path, name=None):
    """Import an OVA appliance."""
    if not os.path.exists(ova_path):
        log.error(f"OVA not found: {ova_path}")
        return False

    args = ["import", ova_path]
    if name:
        args.extend(["--vsys", "0", "--vmname", name])

    log.info(f"Importing OVA: {os.path.basename(ova_path)}...")
    result = vbox.run(args)
    if result is not None:
        disable_all_nics(name or os.path.basename(ova_path).replace(".ova", ""))
    return result is not None


def clone_vm(source_name, new_name):
    """
    Clone an existing VM. Used for live-boot VMs that can't be exported to OVA.
    After cloning, reattaches ISOs from the source and disables leftover NICs
    (the deployer will reassign NICs to the correct subnets).
    Returns True on success.
    """
    if vm_exists(new_name):
        log.info(f"VM '{new_name}' already exists, skipping clone.")
        disable_all_nics(new_name)
        return True

    if not vm_exists(source_name):
        log.error(f"Source VM '{source_name}' not found for cloning.")
        return False

    log.info(f"Cloning '{source_name}' -> '{new_name}'...")
    result = vbox.run(["clonevm", source_name, "--name", new_name, "--register"])
    if result is None:
        return False

    # Disable all NICs on the clone (deployer will set them up correctly)
    disable_all_nics(new_name)

    # Reattach any ISO/DVD media from the source VM
    info = vbox.run(["showvminfo", source_name, "--machinereadable"], check=False)
    if info:
        for line in info.splitlines():
            for port in range(2):
                for device in range(2):
                    key = f'"IDE-{port}-{device}"='
                    if line.startswith(key):
                        path = line.split("=", 1)[1].strip('"')
                        if (path and path != "none" and path != "emptydrive"
                                and path.lower().endswith(".iso")):
                            log.info(f"  Reattaching ISO: {os.path.basename(path)}")
                            vbox.run(["storageattach", new_name,
                                      "--storagectl", "IDE",
                                      "--port", str(port), "--device", str(device),
                                      "--type", "dvddrive", "--medium", path])

    log.info(f"[OK] Cloned '{source_name}' -> '{new_name}'")
    return True


def remove_ide_iso(vm_name):
    """
    Remove all ISO media from a VM's IDE controller.
    Used for VMs like pfSense where the installer ISO must be detached
    so the VM boots from the installed disk instead of the installer.
    """
    info = vbox.run(["showvminfo", vm_name, "--machinereadable"], check=False)
    if not info:
        return

    for line in info.splitlines():
        for port in range(2):
            for device in range(2):
                key = f'"IDE-{port}-{device}"='
                if line.startswith(key):
                    path = line.split("=", 1)[1].strip('"')
                    if (path and path != "none" and path != "emptydrive"
                            and path.lower().endswith(".iso")):
                        log.info(f"  Removing ISO from {vm_name} IDE-{port}-{device}: "
                                 f"{os.path.basename(path)}")
                        vbox.run(["storageattach", vm_name,
                                  "--storagectl", "IDE",
                                  "--port", str(port), "--device", str(device),
                                  "--type", "dvddrive", "--medium", "emptydrive"])


def register_vbox(vbox_path, name=None):
    """
    Register an existing .vbox VM file with VirtualBox.
    The VM is already 'built' — just needs to be added to the registry.

    Returns the actual registered VM name (which may differ from the
    requested name, since .vbox files have their own internal names).
    Returns None on failure.
    """
    if not os.path.exists(vbox_path):
        log.error(f".vbox file not found: {vbox_path}")
        return None

    # Snapshot VM list before registration to detect the new name
    before = set()
    raw = vbox.run(["list", "vms"], check=False) or ""
    for line in raw.splitlines():
        if '"' in line:
            before.add(line.split('"')[1])

    # Check if already registered
    if name and name in before:
        log.info(f"VM '{name}' already registered, skipping.")
        disable_all_nics(name)
        return name

    log.info(f"Registering VM from: {os.path.basename(vbox_path)}...")
    result = vbox.run(["registervm", vbox_path])
    if result is None:
        return None

    # Detect the actual name the VM registered as
    after = set()
    raw = vbox.run(["list", "vms"], check=False) or ""
    for line in raw.splitlines():
        if '"' in line:
            after.add(line.split('"')[1])

    new_vms = after - before
    if len(new_vms) == 1:
        actual_name = new_vms.pop()
        if name and actual_name != name:
            log.info(f"Note: VM registered as '{actual_name}' "
                     f"(requested '{name}')")
        disable_all_nics(actual_name)
        return actual_name

    # Fallback: return the requested name
    if name:
        disable_all_nics(name)
    return name


def setup_image(image_info, vm_name=None):
    """
    Set up a VM from any image type (ISO, OVA, or VBox).

    - ISO: creates a new VM and mounts the ISO
    - OVA: imports the appliance (ready to run)
    - VBox: registers the existing VM (ready to run)

    Returns True on success.
    """
    img_type = image_info.image_type
    name = vm_name or image_info.filename.replace(".ova", "").replace(".iso", "")

    if img_type == "iso":
        # Create new VM + mount ISO
        ok = create_vm(name=name, ostype=image_info.ostype)
        if ok and image_info.path:
            attach_iso(name, image_info.path)
        return ok

    elif img_type == "ova":
        # Import the appliance
        if vm_exists(name):
            log.info(f"VM '{name}' already exists, skipping import.")
            return True
        return import_ova(image_info.path, name=name)

    elif img_type == "vbox":
        # Register the existing VM
        return register_vbox(image_info.path, name=name)

    else:
        log.error(f"Unknown image type: {img_type}")
        return False
