"""
Host-only adapter management - create, list, configure DHCP.
"""

import vbox
from models import Adapter, DHCPConfig
from logger import get_logger

log = get_logger()


def list_adapters():
    """List all host-only adapters currently in VirtualBox."""
    out = vbox.run(["list", "hostonlyifs"], check=False)
    if not out:
        return []

    adapters = []
    current = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Name:"):
            if current.get("name"):
                adapters.append(Adapter(
                    name=current["name"],
                    ip=current.get("ip", ""),
                    netmask=current.get("netmask", "255.255.255.0"),
                ))
            current = {"name": line.split(":", 1)[1].strip()}
        elif line.startswith("IPAddress:"):
            current["ip"] = line.split(":", 1)[1].strip()
        elif line.startswith("NetworkMask:"):
            current["netmask"] = line.split(":", 1)[1].strip()

    # Last one
    if current.get("name"):
        adapters.append(Adapter(
            name=current["name"],
            ip=current.get("ip", ""),
            netmask=current.get("netmask", "255.255.255.0"),
        ))

    return adapters


def find_adapter_by_ip(ip):
    """Find an existing adapter with a specific IP. Returns Adapter or None."""
    for adapter in list_adapters():
        if adapter.ip == ip:
            return adapter
    return None


def create_adapter(ip, netmask="255.255.255.0"):
    """
    Create a host-only adapter and configure its IP.
    If an adapter with this IP already exists, reuse it.
    Returns the adapter name or None on failure.
    """
    # Check if one already exists with this IP
    existing = find_adapter_by_ip(ip)
    if existing:
        log.info(f"[OK] Reusing adapter '{existing.name}' (already has IP {ip})")
        return existing.name

    # Create new adapter
    out = vbox.run(["hostonlyif", "create"])
    if not out or "was successfully created" not in out:
        log.error("Failed to create host-only adapter")
        return None

    # Parse the name VirtualBox assigned
    adapter_name = None
    for line in out.splitlines():
        if "'" in line:
            adapter_name = line.split("'")[1]
            break

    if not adapter_name:
        log.error("Could not parse adapter name from VBoxManage output")
        return None

    # Set IP on the adapter
    result = vbox.run(["hostonlyif", "ipconfig", adapter_name,
                       "--ip", ip, "--netmask", netmask])
    if result is None:
        log.error(f"Failed to configure IP on '{adapter_name}'")
        return None

    log.info(f"[OK] Created adapter '{adapter_name}' -> {ip}/{netmask}")
    return adapter_name


def remove_adapter(name):
    """Remove a host-only adapter."""
    result = vbox.run(["hostonlyif", "remove", name])
    if result is not None:
        log.info(f"[OK] Removed adapter '{name}'")
        return True
    return False


def configure_dhcp(adapter_name, server_ip, netmask, lower_ip, upper_ip, enable=True):
    """
    Configure a DHCP server on a host-only network.
    VBox DHCP servers are keyed by the network name, which for host-only
    adapters is 'HostInterfaceNetworking-<adapter_name>'.
    """
    network_name = f"HostInterfaceNetworking-{adapter_name}"

    # Try to remove existing DHCP server for this network first
    vbox.run(["dhcpserver", "remove", "--network", network_name], check=False)

    if not enable:
        log.info(f"[OK] DHCP disabled on '{adapter_name}'")
        return True

    # Create new DHCP server
    result = vbox.run([
        "dhcpserver", "add",
        "--network", network_name,
        "--server-ip", server_ip,
        "--netmask", netmask,
        "--lower-ip", lower_ip,
        "--upper-ip", upper_ip,
        "--enable",
    ])

    if result is not None:
        log.info(f"[OK] DHCP on '{adapter_name}': {lower_ip} - {upper_ip} "
                 f"(server: {server_ip})")
        return True

    log.error(f"Failed to configure DHCP on '{adapter_name}'")
    return False


def disable_dhcp(adapter_name):
    """Disable DHCP server on a host-only adapter."""
    network_name = f"HostInterfaceNetworking-{adapter_name}"
    vbox.run(["dhcpserver", "remove", "--network", network_name], check=False)
    log.info(f"[OK] DHCP removed from '{adapter_name}'")
