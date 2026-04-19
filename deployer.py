"""
Lab deployment orchestrator - takes a validated LabConfig and builds everything.
"""

import vm_manager
import network_manager
import firewall_manager
import validator
from models import LabConfig
from logger import get_logger

log = get_logger()


def deploy_lab(config, headless=False):
    """
    Deploy a full lab from a LabConfig.

    Steps:
      1. Validate config
      2. Create subnets (host-only adapters + DHCP)
      3. Create VMs + attach ISOs
      4. Assign VMs to subnets
      5. Configure firewalls
      6. Start VMs (firewalls first)

    Returns True on success.
    """
    # ── Step 1: Validate ────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("DEPLOYMENT STARTED")
    log.info("=" * 60)

    errors = validator.validate_lab(config)
    if errors:
        log.error("Validation failed:")
        for e in errors:
            log.error(f"  - {e}")
        return False

    log.info("[OK] Validation passed")

    # Collect firewall VM names for quick lookup
    fw_names = {fw.vm_name for fw in config.firewalls}

    # ── Step 2: Create subnets ──────────────────────────────────────────
    log.info("")
    log.info("[1/5] Creating subnets...")

    for subnet in config.subnets:
        if not network_manager.create_subnet(subnet):
            log.error(f"Failed to create subnet '{subnet.name}'")
            return False

    # ── Step 3: Import/register VMs ──────────────────────────────────────
    log.info("")
    log.info("[2/5] Importing VMs...")

    all_vms = list(config.vms)

    for vm in all_vms:
        img_type = getattr(vm, "image_type", "ova")

        if img_type == "clone":
            ok = vm_manager.clone_vm(vm.iso_path, vm.name)
        elif img_type == "vbox":
            actual_name = vm_manager.register_vbox(vm.iso_path, name=vm.name)
            if actual_name is None:
                ok = False
            else:
                ok = True
                if actual_name != vm.name:
                    log.info(f"Using actual VM name '{actual_name}' "
                             f"for '{vm.name}'")
                    # Update firewall configs if they reference this VM
                    for fw in config.firewalls:
                        if fw.vm_name == vm.name:
                            fw.vm_name = actual_name
                    if vm.name in fw_names:
                        fw_names.discard(vm.name)
                        fw_names.add(actual_name)
                    vm.name = actual_name
        else:
            # OVA import
            if not vm_manager.vm_exists(vm.name):
                ok = vm_manager.import_ova(vm.iso_path, name=vm.name)
            else:
                log.info(f"VM '{vm.name}' already exists, skipping import.")
                vm_manager.disable_all_nics(vm.name)
                ok = True

        if not ok:
            log.error(f"Failed to set up VM '{vm.name}'")
            continue

        # Remove installer ISO from firewall VMs so they boot from disk
        if vm.role == "firewall" and img_type in ("ova", "clone"):
            vm_manager.remove_ide_iso(vm.name)

    # ── Step 4: Assign VMs to subnets ───────────────────────────────────
    log.info("")
    log.info("[3/5] Connecting VMs to subnets...")

    subnet_map = {s.name: s for s in config.subnets}

    for vm in all_vms:
        # Skip firewalls — they get wired up in step 5
        if vm.name in fw_names:
            continue

        for nic_num, subnet_name in enumerate(vm.subnets, 1):
            subnet = subnet_map.get(subnet_name)
            if subnet:
                network_manager.assign_vm_to_subnet(vm.name, subnet, nic_num)
            else:
                log.error(f"Subnet '{subnet_name}' not found for VM '{vm.name}'")

    # ── Step 5: Configure firewalls ──────────────────────────────────────
    if config.firewalls:
        log.info("")
        log.info(f"[4/5] Configuring {len(config.firewalls)} firewall(s)...")
        for fw in config.firewalls:
            firewall_manager.configure_firewall(fw, config.subnets)
    else:
        log.info("")
        log.info("[4/5] No firewalls configured, skipping.")

    # ── Step 6: Start VMs ───────────────────────────────────────────────
    log.info("")
    log.info("[5/5] Starting VMs...")

    # Start firewalls first so they're ready when endpoints boot
    for fw in config.firewalls:
        vm_manager.start_vm(fw.vm_name, headless)

    for vm in all_vms:
        if vm.name in fw_names:
            continue  # Already started
        vm_manager.start_vm(vm.name, headless)

    # ── Done ────────────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 60)
    log.info("DEPLOYMENT COMPLETE")
    log.info("=" * 60)

    return True


def show_lab_status(config=None):
    """Show status of all deployed VMs."""
    if config and config.vms:
        for vm in config.vms:
            state = vm_manager.get_vm_state(vm.name)
            indicator = {
                "running": "[RUNNING]",
                "poweroff": "[OFF]    ",
                "saved": "[SAVED]  ",
            }.get(state, f"[{state.upper():8s}]")

            subnets = ", ".join(vm.subnets) if vm.subnets else "(none)"
            print(f"    {indicator}  {vm.name:20s}  subnets: {subnets}")
    else:
        running = vm_manager.list_running_vms()
        all_vms = vm_manager.list_vms()
        print("  Registered VMs:")
        print(f"    {all_vms or '(none)'}")
        print("\n  Running:")
        print(f"    {running or '(none)'}")


def stop_all(config=None, force=False):
    """Stop all VMs in a lab config, or all running VMs."""
    if config and config.vms:
        for vm in config.vms:
            state = vm_manager.get_vm_state(vm.name)
            if state == "running":
                vm_manager.stop_vm(vm.name, force=force)
    else:
        raw = vm_manager.list_running_vms()
        if raw:
            for line in raw.splitlines():
                if '"' in line:
                    name = line.split('"')[1]
                    vm_manager.stop_vm(name, force=force)


def delete_all(config=None):
    """Delete all VMs in a lab config."""
    if config and config.vms:
        for vm in config.vms:
            state = vm_manager.get_vm_state(vm.name)
            if state == "running":
                vm_manager.stop_vm(vm.name, force=True)
            keep = getattr(vm, "image_type", "ova") == "vbox"
            vm_manager.delete_vm(vm.name, keep_files=keep)
