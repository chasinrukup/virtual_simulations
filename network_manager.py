"""
Network/subnet management - creates subnets by wiring up host-only adapters + DHCP.
"""

import adapter_manager
import vm_manager
from models import Subnet
from logger import get_logger

log = get_logger()


def create_subnet(subnet):
    """
    Create a subnet: host-only adapter + DHCP server.
    Updates subnet.adapter_name with the VBox-assigned name.
    Returns True on success.
    """
    log.info(f"Creating subnet '{subnet.name}' ({subnet.network})")

    # Create or reuse host-only adapter
    adapter_name = adapter_manager.create_adapter(subnet.gateway_ip, subnet.netmask)
    if not adapter_name:
        log.error(f"Failed to create adapter for subnet '{subnet.name}'")
        return False

    subnet.adapter_name = adapter_name

    # Configure DHCP if requested
    if subnet.dhcp and subnet.dhcp.enabled:
        adapter_manager.configure_dhcp(
            adapter_name,
            server_ip=subnet.dhcp.server_ip,
            netmask=subnet.dhcp.netmask,
            lower_ip=subnet.dhcp.lower_ip,
            upper_ip=subnet.dhcp.upper_ip,
            enable=True,
        )
    else:
        # Disable DHCP to keep it clean
        adapter_manager.disable_dhcp(adapter_name)

    log.info(f"[OK] Subnet '{subnet.name}' ready on '{adapter_name}'")
    return True


def destroy_subnet(subnet):
    """Remove adapter and DHCP for a subnet."""
    if subnet.adapter_name:
        adapter_manager.disable_dhcp(subnet.adapter_name)
        adapter_manager.remove_adapter(subnet.adapter_name)
        log.info(f"[OK] Subnet '{subnet.name}' destroyed")


def assign_vm_to_subnet(vm_name, subnet, adapter_num):
    """Connect a VM's NIC to a subnet's host-only adapter."""
    if not subnet.adapter_name:
        log.error(f"Subnet '{subnet.name}' has no adapter assigned")
        return False

    return vm_manager.configure_nic(vm_name, adapter_num, subnet.adapter_name)


def list_existing_subnets():
    """Query VBox for existing host-only adapters and return them."""
    adapters = adapter_manager.list_adapters()
    subnets = []
    for a in adapters:
        if a.ip:
            prefix = ".".join(a.ip.split(".")[:3])
            subnets.append(Subnet(
                name=a.name,
                network=f"{prefix}.0/24",
                gateway_ip=a.ip,
                netmask=a.netmask,
                adapter_name=a.name,
            ))
    return subnets
