"""
Prebuilt mode - fully automated scenarios with zero user configuration.
Each scenario defines subnets, VMs, and firewall setup ready to deploy.
"""

import os
import copy
from models import LabConfig, Subnet, DHCPConfig, VMConfig, FirewallConfig
from logger import get_logger

log = get_logger()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Pre-configured subnets ──────────────────────────────────────────────────

SUBNET_WAN = Subnet(
    name="WAN",
    network="192.168.30.0/24",
    gateway_ip="192.168.30.1",
    netmask="255.255.255.0",
    dhcp=DHCPConfig(
        enabled=True,
        server_ip="192.168.30.2",
        netmask="255.255.255.0",
        lower_ip="192.168.30.100",
        upper_ip="192.168.30.200",
    ),
)

SUBNET_LAN = Subnet(
    name="LAN",
    network="192.168.40.0/24",
    gateway_ip="192.168.40.1",
    netmask="255.255.255.0",
    dhcp=DHCPConfig(
        enabled=True,
        server_ip="192.168.40.2",
        netmask="255.255.255.0",
        lower_ip="192.168.40.100",
        upper_ip="192.168.40.200",
    ),
)

SUBNET_DMZ = Subnet(
    name="DMZ",
    network="192.168.50.0/24",
    gateway_ip="192.168.50.1",
    netmask="255.255.255.0",
    dhcp=DHCPConfig(
        enabled=True,
        server_ip="192.168.50.2",
        netmask="255.255.255.0",
        lower_ip="192.168.50.100",
        upper_ip="192.168.50.200",
    ),
)

SUBNET_MGMT = Subnet(
    name="MGMT",
    network="192.168.60.0/24",
    gateway_ip="192.168.60.1",
    netmask="255.255.255.0",
    dhcp=DHCPConfig(
        enabled=True,
        server_ip="192.168.60.2",
        netmask="255.255.255.0",
        lower_ip="192.168.60.100",
        upper_ip="192.168.60.200",
    ),
)


# ── Scenario Definitions ────────────────────────────────────────────────────

SCENARIOS = [
    # ── Scenario 1: Firewall Basics (2 subnets, 1 firewall, 3 VMs) ──────
    {
        "name": "Firewall Basics",
        "description": (
            "Learn how a firewall routes traffic between two subnets.\n"
            "    pfSense sits between WAN and LAN. Two endpoint VMs — one on\n"
            "    each side — communicate through the firewall.\n"
            "    Concept: Machines on different subnets need a firewall to talk."
        ),
        "layout": (
            "    [vsftpd VM] --( WAN )-- [pfSense] --( LAN )-- [PHP-CGI VM]"
        ),
        "subnets": ["WAN", "LAN"],
        "vms": [
            {
                "name": "WAN_Endpoint",
                "role": "endpoint",
                "subnet": "WAN",
                "source": "emyers_unbuntu_vsftpd.ova",
                "source_type": "ova",
                "ostype": "Ubuntu_64",
                "ram_mb": 2048,
                "cpus": 2,
            },
            {
                "name": "LAN_Endpoint",
                "role": "endpoint",
                "subnet": "LAN",
                "source": "emyers-vulnhu-php",
                "source_type": "clone",
                "ostype": "Debian_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
            {
                "name": "pfSense_FW",
                "role": "firewall",
                "subnet": ["WAN", "LAN"],
                "source": "pfSense_export.ova",
                "source_type": "ova",
                "ostype": "FreeBSD_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
        ],
        "firewalls": [
            {
                "vm_name": "pfSense_FW",
                "wan_subnet": "WAN",
                "lan_subnets": ["LAN"],
            },
        ],
    },

    # ── Scenario 2: Flat Vulnerability Lab (1 subnet, no firewall, 2 VMs) ─
    {
        "name": "Flat Vulnerability Lab",
        "description": (
            "All VMs on one subnet with no firewall — a flat network.\n"
            "    Practice vulnerability scanning and exploitation in an\n"
            "    unrestricted environment. See what happens without segmentation.\n"
            "    Concept: Without a firewall, every machine can reach every other."
        ),
        "layout": (
            "    [vsftpd VM] --( LAN )-- [PHP-CGI VM]"
        ),
        "subnets": ["LAN"],
        "vms": [
            {
                "name": "Target_vsftpd",
                "role": "endpoint",
                "subnet": "LAN",
                "source": "emyers_unbuntu_vsftpd.ova",
                "source_type": "ova",
                "ostype": "Ubuntu_64",
                "ram_mb": 2048,
                "cpus": 2,
            },
            {
                "name": "Target_PHP",
                "role": "endpoint",
                "subnet": "LAN",
                "source": "emyers-vulnhu-php",
                "source_type": "clone",
                "ostype": "Debian_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
        ],
        "firewalls": [],
    },

    # ── Scenario 3: Segmented Attack/Defense (2 subnets, 1 fw, 3 VMs) ────
    {
        "name": "Segmented Attack/Defense",
        "description": (
            "Simulate an attacker on the WAN trying to reach a target on the LAN\n"
            "    through a pfSense firewall. Learn how firewall rules control access\n"
            "    between network segments.\n"
            "    Note: Kali SSH is disabled by default. Enable with:\n"
            "      sudo systemctl enable --now ssh"
        ),
        "layout": (
            "    [Kali Attacker] --( WAN )-- [pfSense] --( LAN )-- [vsftpd Target]"
        ),
        "subnets": ["WAN", "LAN"],
        "vms": [
            {
                "name": "Attacker",
                "role": "endpoint",
                "subnet": "WAN",
                "source": "kali-linux-2025.4-virtualbox-amd64",
                "source_type": "vbox",
                "ostype": "Debian_64",
                "ram_mb": 4096,
                "cpus": 2,
            },
            {
                "name": "Target_vsftpd",
                "role": "endpoint",
                "subnet": "LAN",
                "source": "emyers_unbuntu_vsftpd.ova",
                "source_type": "ova",
                "ostype": "Ubuntu_64",
                "ram_mb": 2048,
                "cpus": 2,
            },
            {
                "name": "pfSense_FW",
                "role": "firewall",
                "subnet": ["WAN", "LAN"],
                "source": "pfSense_export.ova",
                "source_type": "ova",
                "ostype": "FreeBSD_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
        ],
        "firewalls": [
            {
                "vm_name": "pfSense_FW",
                "wan_subnet": "WAN",
                "lan_subnets": ["LAN"],
            },
        ],
    },

    # ── Scenario 4: Multi-Zone Network (3 subnets, 2 firewalls, 4 VMs) ───
    {
        "name": "Multi-Zone Network",
        "description": (
            "Three subnets connected by two firewalls. WAN and LAN are bridged\n"
            "    by Firewall 1. LAN and DMZ are bridged by Firewall 2.\n"
            "    WAN CANNOT reach DMZ directly — traffic must pass through both.\n"
            "    Concept: Selective connectivity — firewalls control which subnets talk."
        ),
        "layout": (
            "    [vsftpd] --( WAN )-- [FW1] --( LAN )-- [FW2] --( DMZ )-- [PHP-CGI]"
        ),
        "subnets": ["WAN", "LAN", "DMZ"],
        "vms": [
            {
                "name": "WAN_Server",
                "role": "endpoint",
                "subnet": "WAN",
                "source": "emyers_unbuntu_vsftpd.ova",
                "source_type": "ova",
                "ostype": "Ubuntu_64",
                "ram_mb": 2048,
                "cpus": 2,
            },
            {
                "name": "DMZ_Server",
                "role": "endpoint",
                "subnet": "DMZ",
                "source": "emyers-vulnhu-php",
                "source_type": "clone",
                "ostype": "Debian_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
            {
                "name": "Firewall_1",
                "role": "firewall",
                "subnet": ["WAN", "LAN"],
                "source": "pfSense_export.ova",
                "source_type": "ova",
                "ostype": "FreeBSD_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
            {
                "name": "Firewall_2",
                "role": "firewall",
                "subnet": ["LAN", "DMZ"],
                "source": "pfSense_export.ova",
                "source_type": "ova",
                "ostype": "FreeBSD_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
        ],
        "firewalls": [
            {
                "vm_name": "Firewall_1",
                "wan_subnet": "WAN",
                "lan_subnets": ["LAN"],
            },
            {
                "vm_name": "Firewall_2",
                "wan_subnet": "LAN",
                "lan_subnets": ["DMZ"],
            },
        ],
    },

    # ── Scenario 5: Full Enterprise (3 subnets, 1 firewall, 4 VMs) ───────
    {
        "name": "Enterprise Network",
        "description": (
            "One firewall protecting multiple zones: WAN (external), LAN (internal),\n"
            "    and DMZ (servers). The firewall routes between all three.\n"
            "    An attacker on the WAN tries to reach servers on LAN and DMZ.\n"
            "    Concept: One firewall can manage multiple internal zones."
        ),
        "layout": (
            "                    ( WAN )-- [Kali Attacker]\n"
            "                      |\n"
            "    [vsftpd] --( LAN )-- [pfSense] --( DMZ )-- [PHP-CGI]"
        ),
        "subnets": ["WAN", "LAN", "DMZ"],
        "vms": [
            {
                "name": "Attacker",
                "role": "endpoint",
                "subnet": "WAN",
                "source": "kali-linux-2025.4-virtualbox-amd64",
                "source_type": "vbox",
                "ostype": "Debian_64",
                "ram_mb": 4096,
                "cpus": 2,
            },
            {
                "name": "Internal_Server",
                "role": "endpoint",
                "subnet": "LAN",
                "source": "emyers_unbuntu_vsftpd.ova",
                "source_type": "ova",
                "ostype": "Ubuntu_64",
                "ram_mb": 2048,
                "cpus": 2,
            },
            {
                "name": "DMZ_Server",
                "role": "endpoint",
                "subnet": "DMZ",
                "source": "emyers-vulnhu-php",
                "source_type": "clone",
                "ostype": "Debian_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
            {
                "name": "pfSense_FW",
                "role": "firewall",
                "subnet": ["WAN", "LAN", "DMZ"],
                "source": "pfSense_export.ova",
                "source_type": "ova",
                "ostype": "FreeBSD_64",
                "ram_mb": 1024,
                "cpus": 1,
            },
        ],
        "firewalls": [
            {
                "vm_name": "pfSense_FW",
                "wan_subnet": "WAN",
                "lan_subnets": ["LAN", "DMZ"],
            },
        ],
    },
]


# ── Subnet lookup ────────────────────────────────────────────────────────────

_SUBNET_MAP = {
    "WAN": SUBNET_WAN,
    "LAN": SUBNET_LAN,
    "DMZ": SUBNET_DMZ,
    "MGMT": SUBNET_MGMT,
}


def get_subnet(name):
    """Return a deep copy of a named subnet."""
    return copy.deepcopy(_SUBNET_MAP[name])


# ── Resolve source paths ────────────────────────────────────────────────────

def _find_file(filename, directory=None):
    """Recursively search for a file in the project directory."""
    if directory is None:
        directory = BASE_DIR
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f == filename:
                return os.path.join(root, f)
        # Also check folder names (for .vbox)
        for d in dirs:
            if d == filename:
                folder = os.path.join(root, d)
                for vf in os.listdir(folder):
                    if vf.lower().endswith(".vbox"):
                        return os.path.join(folder, vf)
    return None


def resolve_source(vm_def):
    """
    Resolve the source path for a VM definition.
    Returns (path_or_name, source_type) or (None, None) if not found.
    """
    src = vm_def["source"]
    src_type = vm_def["source_type"]

    if src_type == "clone":
        import vm_manager
        if vm_manager.vm_exists(src):
            return src, "clone"
        return None, None

    elif src_type == "ova":
        path = _find_file(src)
        if path and os.path.getsize(path) > 1_000_000:
            return path, "ova"
        return None, None

    elif src_type == "vbox":
        path = _find_file(src)
        if path:
            return path, "vbox"
        return None, None

    return None, None


def check_scenario(scenario):
    """
    Check if all required images for a scenario are available.
    Returns (ok, missing_list).
    """
    missing = []
    for vm_def in scenario["vms"]:
        path, stype = resolve_source(vm_def)
        if path is None:
            missing.append(f"{vm_def['name']} ({vm_def['source']})")
    return len(missing) == 0, missing


def build_scenario_config(scenario):
    """
    Build a complete LabConfig from a scenario definition.
    Returns LabConfig or None on error.
    """
    # Build subnets
    subnets = [get_subnet(name) for name in scenario["subnets"]]

    # Build VMs
    vms = []
    for vm_def in scenario["vms"]:
        source_path, source_type = resolve_source(vm_def)
        if source_path is None:
            log.error(f"Cannot find source for '{vm_def['name']}': {vm_def['source']}")
            return None

        subnet_list = vm_def["subnet"]
        if isinstance(subnet_list, str):
            subnet_list = [subnet_list]

        vms.append(VMConfig(
            name=vm_def["name"],
            ostype=vm_def["ostype"],
            ram_mb=vm_def["ram_mb"],
            cpus=vm_def["cpus"],
            disk_mb=0,
            iso_path=source_path,
            image_type=source_type,
            role=vm_def["role"],
            subnets=subnet_list,
        ))

    # Build config
    config = LabConfig(subnets=subnets, vms=vms)

    # Firewalls
    fw_list = scenario.get("firewalls", [])
    # Backward compat: old format had single "firewall" key
    if not fw_list and scenario.get("firewall"):
        fw_list = [scenario["firewall"]]

    for fw_def in fw_list:
        config.firewalls.append(FirewallConfig(
            vm_name=fw_def["vm_name"],
            wan_subnet=fw_def["wan_subnet"],
            lan_subnets=fw_def["lan_subnets"],
        ))

    return config
