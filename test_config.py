#!/usr/bin/env python3
"""
Test Script - Simulates the network builder interface WITHOUT deploying VMs
Use this to test your configuration and see what selections look like
"""

import json
import os


def print_header(text):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")


def print_section(text):
    print(f"\n>>> {text}")
    print("-" * 80)


def test_vm_inventory():
    """Test loading and displaying VM inventory"""
    print_header("VM Inventory Test")
    
    config_file = "vm_inventory.json"
    
    if not os.path.exists(config_file):
        print(f"❌ Config file not found: {config_file}")
        print("\nCreate vm_inventory.json first!")
        return False
    
    print(f"✓ Found config file: {config_file}")
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    available_vms = config.get('available_vms', {})
    
    print_section("Available VMs")
    
    total_count = 0
    vm_list = []
    
    for category, vms in available_vms.items():
        print(f"\n[{category}]")
        for vm in vms:
            total_count += 1
            name = vm.get('name', 'Unknown')
            vm_type = vm.get('type', 'Unknown')
            ram = vm.get('ram_mb', 'N/A')
            cpus = vm.get('cpus', 'N/A')
            path = vm.get('path', '')
            
            print(f"  {total_count}. {name}")
            print(f"      Type: {vm_type} | RAM: {ram}MB | CPUs: {cpus}")
            
            # Check if file exists
            if path:
                if os.path.exists(path):
                    print(f"      Path: {path} ✓")
                else:
                    print(f"      Path: {path} ❌ (NOT FOUND)")
            else:
                print(f"      Path: (not specified)")
            
            vm_list.append(vm)
    
    print(f"\n{'='*80}")
    print(f"Total VMs: {total_count}")
    
    # Count by type
    firewalls = [vm for vms in available_vms.values() for vm in vms if 'firewall' in vm.get('type', '').lower()]
    regular_vms = [vm for vms in available_vms.values() for vm in vms if 'firewall' not in vm.get('type', '').lower()]
    
    print(f"  • Regular VMs: {len(regular_vms)}")
    print(f"  • Firewall VMs: {len(firewalls)}")
    
    # Check for missing paths
    missing_paths = [vm for vms in available_vms.values() for vm in vms if vm.get('path', '') and not os.path.exists(vm.get('path', ''))]
    
    if missing_paths:
        print(f"\n⚠ Warning: {len(missing_paths)} VM(s) have invalid paths!")
        print("These VMs will fail to import. Fix the paths in vm_inventory.json:")
        for vm in missing_paths:
            print(f"  • {vm.get('name', 'Unknown')}: {vm.get('path', 'N/A')}")
    
    return True


def simulate_demo_scenario():
    """Simulate a typical demo scenario"""
    print_header("Demo Scenario Simulation")
    
    print("Simulating a 2-subnet setup with 3 VMs and 1 firewall:\n")
    
    print("USER SELECTIONS:")
    print("  Number of subnets: 2")
    print("  Subnet 1: IT_Subnet (192.168.40.0/24)")
    print("  Subnet 2: OT_Subnet (192.168.60.0/24)")
    print("\nVM ASSIGNMENTS:")
    print("  IT_Subnet:")
    print("    • VM1_Debian")
    print("    • VM2_Ubuntu")
    print("  OT_Subnet:")
    print("    • VM3_CentOS")
    print("\nFIREWALL CONFIGURATION:")
    print("  pfSense_FW1:")
    print("    WAN ← IT_Subnet (192.168.40.1)")
    print("    LAN → OT_Subnet (192.168.60.1)")
    
    print("\n" + "="*80)
    print("RESULTING NETWORK TOPOLOGY:")
    print("="*80)
    print("""
    IT Subnet (192.168.40.0/24)              OT Subnet (192.168.60.0/24)
    ────────────────────────                 ────────────────────────
    
    ┌─────────────┐
    │ VM1_Debian  │ (192.168.40.10)
    └──────┬──────┘
           │
    ┌──────┴──────┐
    │ VM2_Ubuntu  │ (192.168.40.11)
    └──────┬──────┘
           │
           ├─────── [192.168.40.0/24] ────┐
                                           │
                                    ┌──────┴──────┐
                                    │  pfSense    │
                                    │  Firewall   │
                                    │             │
                                    │ WAN: .40.1  │
                                    │ LAN: .60.1  │
                                    └──────┬──────┘
                                           │
           ┌─────── [192.168.60.0/24] ────┘
           │
    ┌──────┴──────┐
    │ VM3_CentOS  │ (192.168.60.10)
    └─────────────┘
    """)
    
    print("="*80)
    print("CONNECTIVITY TESTS:")
    print("="*80)
    print("  VM1_Debian → pfSense WAN (192.168.40.1)    : ✓ Same subnet")
    print("  VM2_Ubuntu → pfSense WAN (192.168.40.1)    : ✓ Same subnet")
    print("  VM3_CentOS → pfSense LAN (192.168.60.1)    : ✓ Same subnet")
    print("  VM1_Debian → VM3_CentOS (192.168.60.10)    : ✓ Through firewall")
    print("  VM2_Ubuntu → VM3_CentOS (192.168.60.10)    : ✓ Through firewall")


def check_prerequisites():
    """Check if everything is ready"""
    print_header("Prerequisites Check")
    
    checks = []
    
    # Check Python version
    import sys
    python_version = sys.version_info
    if python_version >= (3, 6):
        print("✓ Python version OK:", f"{python_version.major}.{python_version.minor}.{python_version.micro}")
        checks.append(True)
    else:
        print("❌ Python version too old:", f"{python_version.major}.{python_version.minor}")
        checks.append(False)
    
    # Check for required modules
    try:
        import paramiko
        print("✓ paramiko module installed")
        checks.append(True)
    except ImportError:
        print("❌ paramiko module NOT installed")
        print("   Install with: pip install paramiko")
        checks.append(False)
    
    # Check for config file
    if os.path.exists("vm_inventory.json"):
        print("✓ vm_inventory.json found")
        checks.append(True)
    else:
        print("❌ vm_inventory.json NOT found")
        print("   Create this file with your VM paths!")
        checks.append(False)
    
    # Check for VBoxManage (Windows)
    vbox_paths = [
        "C:\\Program Files\\Oracle\\VirtualBox\\VBoxManage.exe",
        "C:\\Program Files (x86)\\Oracle\\VirtualBox\\VBoxManage.exe"
    ]
    
    vbox_found = any(os.path.exists(p) for p in vbox_paths)
    
    if vbox_found:
        print("✓ VirtualBox found")
        checks.append(True)
    else:
        print("⚠ VirtualBox not found in standard location")
        print("   Make sure VirtualBox is installed")
        checks.append(False)
    
    print("\n" + "="*80)
    if all(checks):
        print("✅ All checks passed! You're ready to run the network builder.")
    else:
        print("⚠ Some checks failed. Fix these issues before deploying.")
    
    return all(checks)


def main():
    """Run all tests"""
    print_header("VM Network Builder - Pre-Flight Test")
    
    print("This script tests your configuration WITHOUT deploying VMs")
    print("Use this to verify everything is set up correctly before demo day.\n")
    
    # Run checks
    all_good = check_prerequisites()
    
    print()
    
    if os.path.exists("vm_inventory.json"):
        test_vm_inventory()
    
    print()
    simulate_demo_scenario()
    
    print_header("Test Complete")
    
    if all_good:
        print("✅ Everything looks good!")
        print("\nNext steps:")
        print("  1. Verify all VM paths in vm_inventory.json are correct")
        print("  2. Run: python network_builder.py")
        print("  3. Follow the interactive prompts")
        print("  4. Demo to Rakesh on Saturday!")
    else:
        print("⚠ Fix the issues above before running network_builder.py")
    
    print()


if __name__ == "__main__":
    main()
