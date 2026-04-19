"""
Data models for the Network Simulation Orchestrator.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# VBoxManage OS type mappings
OS_TYPES = {
    "debian":   "Debian_64",
    "ubuntu":   "Ubuntu_64",
    "pfsense":  "FreeBSD_64",
    "netgate":  "FreeBSD_64",
    "freebsd":  "FreeBSD_64",
    "centos":   "RedHat_64",
    "kali":     "Debian_64",
    "windows":  "Windows10_64",
    "other":    "Other_64",
}


def guess_ostype(filename):
    """Guess VBox OS type from a filename."""
    name = filename.lower()
    for key, ostype in OS_TYPES.items():
        if key in name:
            return ostype
    return "Other_64"


@dataclass
class Adapter:
    """A VirtualBox host-only network adapter."""
    name: str                        # VBox-assigned name (e.g., "VirtualBox Host-Only Ethernet Adapter #2")
    ip: str = ""                     # IPv4 address on the adapter
    netmask: str = "255.255.255.0"


@dataclass
class DHCPConfig:
    """DHCP server config for a host-only adapter."""
    enabled: bool = True
    server_ip: str = ""             # DHCP server address
    lower_ip: str = ""              # Start of IP pool
    upper_ip: str = ""              # End of IP pool
    netmask: str = "255.255.255.0"


@dataclass
class Subnet:
    """A network subnet mapped to one host-only adapter."""
    name: str                        # User-friendly name (e.g., "IT_Subnet")
    network: str                     # e.g., "192.168.30.0/24"
    gateway_ip: str                  # e.g., "192.168.30.1"
    netmask: str = "255.255.255.0"
    adapter_name: str = ""           # VBox host-only adapter assigned to this subnet
    dhcp: Optional[DHCPConfig] = None


@dataclass
class VMConfig:
    """Configuration for a virtual machine."""
    name: str
    ostype: str = "Debian_64"
    ram_mb: int = 2048
    cpus: int = 2
    disk_mb: int = 20000
    iso_path: str = ""               # path to OVA, .vbox file, or source VM name (for clone)
    image_type: str = "ova"          # "ova", "vbox", or "clone"
    role: str = "endpoint"           # "endpoint" or "firewall"
    subnets: List[str] = field(default_factory=list)  # subnet names this VM connects to


@dataclass
class FirewallConfig:
    """Firewall routing configuration."""
    vm_name: str                     # Name of the firewall VM
    wan_subnet: str                  # Subnet name for WAN interface
    lan_subnets: List[str] = field(default_factory=list)  # Subnet names for LAN interfaces


@dataclass
class LabConfig:
    """Complete lab configuration - everything needed to deploy."""
    subnets: List[Subnet] = field(default_factory=list)
    vms: List[VMConfig] = field(default_factory=list)
    firewalls: List[FirewallConfig] = field(default_factory=list)

    # Backward compatibility: single firewall property
    @property
    def firewall(self):
        return self.firewalls[0] if self.firewalls else None

    @firewall.setter
    def firewall(self, value):
        if value is None:
            self.firewalls = []
        elif self.firewalls:
            self.firewalls[0] = value
        else:
            self.firewalls.append(value)


@dataclass
class ImageInfo:
    """Information about a discovered VM image (ISO, OVA, or VBox folder)."""
    filename: str
    path: str
    size_mb: int
    ostype: str
    image_type: str = "iso"  # "iso", "ova", or "vbox"
    role: str = ""           # "endpoint" or "firewall", persisted in iso_roles.json


# Keep backward compatibility
ISOInfo = ImageInfo
