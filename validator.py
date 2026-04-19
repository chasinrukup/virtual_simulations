"""
Validation layer - checks lab config before deployment.
All functions return a list of error strings. Empty list = valid.
"""

from models import LabConfig, Subnet, VMConfig, FirewallConfig
from typing import List


def validate_no_duplicate_adapters(subnets: List[Subnet]) -> List[str]:
    """Each subnet must map to a unique adapter."""
    errors = []
    seen = {}
    for s in subnets:
        if not s.adapter_name:
            continue
        if s.adapter_name in seen:
            errors.append(
                f"Adapter '{s.adapter_name}' used by both "
                f"'{seen[s.adapter_name]}' and '{s.name}'"
            )
        else:
            seen[s.adapter_name] = s.name
    return errors


def validate_dhcp_range(subnet: Subnet) -> List[str]:
    """DHCP range must be valid within the subnet."""
    errors = []
    if not subnet.dhcp or not subnet.dhcp.enabled:
        return errors

    dhcp = subnet.dhcp

    # Parse last octet for simple range check
    try:
        lower_last = int(dhcp.lower_ip.split(".")[-1])
        upper_last = int(dhcp.upper_ip.split(".")[-1])
        gateway_last = int(subnet.gateway_ip.split(".")[-1])

        if lower_last >= upper_last:
            errors.append(
                f"Subnet '{subnet.name}': DHCP lower ({dhcp.lower_ip}) "
                f"must be less than upper ({dhcp.upper_ip})"
            )

        if lower_last <= gateway_last:
            errors.append(
                f"Subnet '{subnet.name}': DHCP range starts at {dhcp.lower_ip} "
                f"which overlaps with gateway {subnet.gateway_ip}"
            )

        # Check same network prefix
        lower_prefix = ".".join(dhcp.lower_ip.split(".")[:3])
        upper_prefix = ".".join(dhcp.upper_ip.split(".")[:3])
        gw_prefix = ".".join(subnet.gateway_ip.split(".")[:3])

        if lower_prefix != gw_prefix or upper_prefix != gw_prefix:
            errors.append(
                f"Subnet '{subnet.name}': DHCP range not in same /24 as gateway"
            )

    except (ValueError, IndexError):
        errors.append(f"Subnet '{subnet.name}': Invalid IP format in DHCP config")

    return errors


def validate_firewall(firewall: FirewallConfig, subnets: List[Subnet]) -> List[str]:
    """Firewall must connect to at least 2 subnets (WAN + LAN)."""
    errors = []
    if not firewall:
        return errors

    subnet_names = {s.name for s in subnets}

    if not firewall.wan_subnet:
        errors.append("Firewall has no WAN subnet assigned")
    elif firewall.wan_subnet not in subnet_names:
        errors.append(f"Firewall WAN subnet '{firewall.wan_subnet}' does not exist")

    if not firewall.lan_subnets:
        errors.append("Firewall has no LAN subnet(s) assigned")
    else:
        for lan in firewall.lan_subnets:
            if lan not in subnet_names:
                errors.append(f"Firewall LAN subnet '{lan}' does not exist")
            if lan == firewall.wan_subnet:
                errors.append(f"Firewall LAN and WAN cannot be the same subnet ('{lan}')")

    total_nics = 1 + len(firewall.lan_subnets)  # WAN + LANs
    if total_nics > 4:
        errors.append(f"Firewall needs {total_nics} NICs but VirtualBox max is 4")

    return errors


def validate_vm_adapters(vms: List[VMConfig]) -> List[str]:
    """Each VM's subnet count must not exceed 4 (VBox NIC limit)."""
    errors = []
    for vm in vms:
        if len(vm.subnets) > 4:
            errors.append(
                f"VM '{vm.name}' assigned to {len(vm.subnets)} subnets "
                f"but max is 4 NICs"
            )
        if not vm.subnets:
            errors.append(f"VM '{vm.name}' has no subnet assigned")
    return errors


def validate_subnet_no_overlap(subnets: List[Subnet]) -> List[str]:
    """No two subnets should share the same network prefix."""
    errors = []
    seen = {}
    for s in subnets:
        prefix = ".".join(s.gateway_ip.split(".")[:3])
        if prefix in seen:
            errors.append(
                f"Subnets '{seen[prefix]}' and '{s.name}' "
                f"share the same network prefix {prefix}.x"
            )
        else:
            seen[prefix] = s.name
    return errors


def validate_lab(config: LabConfig) -> List[str]:
    """Run all validations on a complete lab config. Returns all errors."""
    errors = []
    errors.extend(validate_no_duplicate_adapters(config.subnets))
    errors.extend(validate_subnet_no_overlap(config.subnets))
    for s in config.subnets:
        errors.extend(validate_dhcp_range(s))
    errors.extend(validate_vm_adapters(config.vms))
    for fw in config.firewalls:
        errors.extend(validate_firewall(fw, config.subnets))
    # Check no two firewalls share the same VM
    fw_vm_names = [fw.vm_name for fw in config.firewalls]
    if len(fw_vm_names) != len(set(fw_vm_names)):
        errors.append("Multiple firewalls cannot use the same VM")
    return errors
