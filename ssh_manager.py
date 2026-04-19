#!/usr/bin/env python3
"""
SSH Manager - handles SSH connections to VMs for post-deploy configuration.
Requires: pip install paramiko
"""

import time


class SSHManager:
    """Manages SSH connections to deployed VMs."""

    def __init__(self):
        self.connections = {}
        self._paramiko = None

    def _get_paramiko(self):
        """Lazy import paramiko so the rest of the app works without it."""
        if self._paramiko is None:
            try:
                import paramiko
                self._paramiko = paramiko
            except ImportError:
                print("  [WARN] paramiko not installed. SSH features unavailable.")
                print("         Install with: pip install paramiko")
                return None
        return self._paramiko

    def connect(self, host, username, password, port=22, timeout=10):
        """Open an SSH connection to a VM."""
        paramiko = self._get_paramiko()
        if not paramiko:
            return False

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, port=port, username=username,
                           password=password, timeout=timeout)
            self.connections[host] = client
            print(f"  [OK] SSH connected to {host}")
            return True
        except Exception as e:
            print(f"  [ERROR] SSH to {host} failed: {e}")
            return False

    def run_command(self, host, command):
        """Run a command on a connected VM."""
        client = self.connections.get(host)
        if not client:
            print(f"  [ERROR] No SSH connection to {host}")
            return None

        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=30)
            output = stdout.read().decode().strip()
            errors = stderr.read().decode().strip()
            if errors:
                print(f"  [STDERR] {errors}")
            return output
        except Exception as e:
            print(f"  [ERROR] Command failed on {host}: {e}")
            return None

    def configure_static_ip(self, host, interface, ip, netmask, gateway=None):
        """Configure a static IP on a Debian/Ubuntu VM."""
        commands = [
            f"sudo ip addr flush dev {interface}",
            f"sudo ip addr add {ip}/{netmask} dev {interface}",
            f"sudo ip link set {interface} up",
        ]
        if gateway:
            commands.append(f"sudo ip route add default via {gateway}")

        for cmd in commands:
            self.run_command(host, cmd)

        print(f"  [OK] Configured {interface} = {ip} on {host}")

    def disconnect(self, host):
        """Close SSH connection."""
        client = self.connections.pop(host, None)
        if client:
            client.close()

    def disconnect_all(self):
        """Close all SSH connections."""
        for host in list(self.connections.keys()):
            self.disconnect(host)
