"""
Low-level VBoxManage command runner.
Single point of contact for all VirtualBox CLI operations.
"""

import subprocess
import os
import sys
from logger import get_logger

VBOXMANAGE = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"

log = get_logger()


def check_vbox():
    """Verify VBoxManage is available."""
    if not os.path.exists(VBOXMANAGE):
        log.error(f"VBoxManage not found at: {VBOXMANAGE}")
        sys.exit(1)


def run(args, check=True):
    """
    Run a VBoxManage command.

    Returns stdout on success, None on failure.
    """
    cmd = [VBOXMANAGE] + args
    cmd_str = " ".join(args[:3])  # log first 3 args for readability
    log.debug(f"VBoxManage {' '.join(args)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        if result.stdout.strip():
            log.debug(f"  stdout: {result.stdout.strip()[:200]}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        log.error(f"VBoxManage {cmd_str}... failed: {e.stderr.strip()}")
        return None
