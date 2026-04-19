"""
Configuration persistence - save/load lab configs, ISO roles, ISO scanning.
"""

import os
import json
from models import (LabConfig, Subnet, VMConfig, FirewallConfig,
                    DHCPConfig, ImageInfo, ISOInfo, guess_ostype)
from logger import get_logger

log = get_logger()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ISO_ROLES_FILE = os.path.join(BASE_DIR, "iso_roles.json")
CONFIGS_DIR = os.path.join(BASE_DIR, "configs")


# ── ISO Roles ───────────────────────────────────────────────────────────────

def load_iso_roles():
    """Load saved ISO role classifications."""
    if os.path.exists(ISO_ROLES_FILE):
        with open(ISO_ROLES_FILE, "r") as f:
            return json.load(f)
    return {}


def save_iso_roles(roles):
    """Save ISO role classifications."""
    with open(ISO_ROLES_FILE, "w") as f:
        json.dump(roles, f, indent=2)
    log.debug(f"ISO roles saved to {ISO_ROLES_FILE}")


# ── Image Scanning (ISOs, OVAs, VBox VMs) ───────────────────────────────────

def scan_images(directory=None):
    """
    Find all OVA appliances and VirtualBox VM folders (.vbox) recursively.
    Returns list of ImageInfo.
    """
    if directory is None:
        directory = BASE_DIR

    images = []
    if not os.path.isdir(directory):
        log.error(f"Directory not found: {directory}")
        return images

    saved_roles = load_iso_roles()
    seen_vbox_dirs = set()

    for root, dirs, files in os.walk(directory):
        for f in sorted(files):
            path = os.path.join(root, f)
            lower = f.lower()

            if lower.endswith(".ova"):
                images.append(ImageInfo(
                    filename=f,
                    path=path,
                    size_mb=round(os.path.getsize(path) / 1048576),
                    ostype=guess_ostype(f),
                    image_type="ova",
                    role=saved_roles.get(f, ""),
                ))

            elif lower.endswith(".vbox"):
                folder = os.path.dirname(path)
                if folder in seen_vbox_dirs:
                    continue
                seen_vbox_dirs.add(folder)

                folder_name = os.path.basename(folder)
                total_size = 0
                for disk_f in os.listdir(folder):
                    if disk_f.lower().endswith((".vdi", ".vmdk")):
                        total_size += os.path.getsize(os.path.join(folder, disk_f))

                images.append(ImageInfo(
                    filename=folder_name,
                    path=path,
                    size_mb=round(total_size / 1048576),
                    ostype=guess_ostype(folder_name),
                    image_type="vbox",
                    role=saved_roles.get(folder_name, ""),
                ))

    return images




# ── Lab Config Save/Load ───────────────────────────────────────────────────

def _subnet_to_dict(s):
    d = {"name": s.name, "network": s.network, "gateway_ip": s.gateway_ip,
         "netmask": s.netmask, "adapter_name": s.adapter_name}
    if s.dhcp:
        d["dhcp"] = {
            "enabled": s.dhcp.enabled, "server_ip": s.dhcp.server_ip,
            "netmask": s.dhcp.netmask, "lower_ip": s.dhcp.lower_ip,
            "upper_ip": s.dhcp.upper_ip,
        }
    return d


def _subnet_from_dict(d):
    dhcp = None
    if "dhcp" in d:
        dhcp = DHCPConfig(**d["dhcp"])
    return Subnet(
        name=d["name"], network=d["network"], gateway_ip=d["gateway_ip"],
        netmask=d.get("netmask", "255.255.255.0"),
        adapter_name=d.get("adapter_name", ""), dhcp=dhcp,
    )


def save_lab_config(config, path=None):
    """Save a LabConfig to JSON."""
    if path is None:
        os.makedirs(CONFIGS_DIR, exist_ok=True)
        path = os.path.join(CONFIGS_DIR, "lab_config.json")

    data = {
        "subnets": [_subnet_to_dict(s) for s in config.subnets],
        "vms": [
            {"name": vm.name, "ostype": vm.ostype, "ram_mb": vm.ram_mb,
             "cpus": vm.cpus, "disk_mb": vm.disk_mb, "iso_path": vm.iso_path,
             "image_type": getattr(vm, "image_type", "iso"),
             "role": vm.role, "subnets": vm.subnets}
            for vm in config.vms
        ],
    }
    if config.firewalls:
        data["firewalls"] = [
            {
                "vm_name": fw.vm_name,
                "wan_subnet": fw.wan_subnet,
                "lan_subnets": fw.lan_subnets,
            }
            for fw in config.firewalls
        ]

    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    log.info(f"[OK] Lab config saved to {path}")
    return path


def load_lab_config(path):
    """Load a LabConfig from JSON."""
    if not os.path.exists(path):
        log.error(f"Config file not found: {path}")
        return None

    with open(path, "r") as f:
        data = json.load(f)

    config = LabConfig()
    config.subnets = [_subnet_from_dict(s) for s in data.get("subnets", [])]
    config.vms = [
        VMConfig(name=v["name"], ostype=v.get("ostype", "Debian_64"),
                 ram_mb=v.get("ram_mb", 2048), cpus=v.get("cpus", 2),
                 disk_mb=v.get("disk_mb", 20000), iso_path=v.get("iso_path", ""),
                 image_type=v.get("image_type", "iso"),
                 role=v.get("role", "endpoint"), subnets=v.get("subnets", []))
        for v in data.get("vms", [])
    ]
    # Support both new "firewalls" list and old single "firewall" key
    fw_list = data.get("firewalls", [])
    if not fw_list and data.get("firewall"):
        fw_list = [data["firewall"]]
    for fw in fw_list:
        config.firewalls.append(FirewallConfig(
            vm_name=fw["vm_name"],
            wan_subnet=fw["wan_subnet"],
            lan_subnets=fw.get("lan_subnets", []),
        ))

    log.info(f"[OK] Lab config loaded from {path}")
    return config
