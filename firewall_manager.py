"""
Firewall setup - assign WAN/LAN interfaces on a firewall VM.
"""

import vm_manager
import network_manager
from models import FirewallConfig, Subnet
from typing import List
from logger import get_logger

log = get_logger()


def configure_firewall(fw_config, subnets):
    """
    Wire the firewall VM's NICs to the correct subnets.
    NIC 1 = WAN subnet, NIC 2+ = LAN subnets.

    fw_config: FirewallConfig
    subnets:   list of Subnet objects (to look up adapter names)
    """
    subnet_map = {s.name: s for s in subnets}
    vm_name = fw_config.vm_name

    # NIC 1 -> WAN
    wan = subnet_map.get(fw_config.wan_subnet)
    if not wan:
        log.error(f"WAN subnet '{fw_config.wan_subnet}' not found")
        return False

    log.info(f"Firewall '{vm_name}' WAN -> {wan.name} ({wan.adapter_name})")
    if not network_manager.assign_vm_to_subnet(vm_name, wan, adapter_num=1):
        return False

    # NIC 2+ -> LAN subnets
    for i, lan_name in enumerate(fw_config.lan_subnets):
        lan = subnet_map.get(lan_name)
        if not lan:
            log.error(f"LAN subnet '{lan_name}' not found")
            return False

        nic_num = i + 2  # NIC 2, 3, 4...
        if nic_num > 4:
            log.error(f"Cannot assign more than 4 NICs (trying NIC {nic_num})")
            return False

        log.info(f"Firewall '{vm_name}' LAN{i+1} -> {lan.name} ({lan.adapter_name})")
        if not network_manager.assign_vm_to_subnet(vm_name, lan, adapter_num=nic_num):
            return False

    log.info(f"[OK] Firewall '{vm_name}' configured: "
             f"WAN={fw_config.wan_subnet}, "
             f"LAN={', '.join(fw_config.lan_subnets)}")
    return True
