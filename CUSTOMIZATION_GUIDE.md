# How to Customize the VM Network Builder

## Quick Setup for Your Demo (3 VMs + 2 Firewalls)

### Step 1: Edit `vm_inventory.json`

This file contains all your available VMs. You need to update the **paths** to match your actual VM locations.

**What to change:**

```json
{
  "vm_directory": "C:\\VMs\\OVAs",  ← CHANGE THIS to your actual VM directory
  
  "available_vms": {
    "IT_VMs": [
      {
        "name": "VM1_Debian",
        "path": "C:\\VMs\\OVAs\\debian_vm1.ova",  ← CHANGE THIS to actual path
        ...
      }
    ]
  }
}
```

### Step 2: Find Your VM Paths

**On Windows:**
1. Open File Explorer
2. Navigate to where you saved your VMs
3. Right-click on a VM file → Properties → Copy the full path
4. Example: `C:\Users\Sachin\VirtualBox VMs\Debian1.ova`

**Example paths you might have:**
```
C:\Users\Sachin\VirtualBox VMs\Debian1.ova
C:\Users\Sachin\VirtualBox VMs\Debian2.ova
C:\Users\Sachin\Downloads\pfsense.ova
D:\VMs\ubuntu.ova
```

### Step 3: Update vm_inventory.json with YOUR paths

Here's a template with placeholders - **replace these with your actual paths**:

```json
{
  "vm_directory": "PUT_YOUR_VM_FOLDER_HERE",
  
  "available_vms": {
    "IT_VMs": [
      {
        "name": "VM1_Debian",
        "path": "PUT_PATH_TO_YOUR_FIRST_VM_HERE",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password",
        "description": "First test VM"
      },
      {
        "name": "VM2_Debian",
        "path": "PUT_PATH_TO_YOUR_SECOND_VM_HERE",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password",
        "description": "Second test VM"
      },
      {
        "name": "VM3_Ubuntu",
        "path": "PUT_PATH_TO_YOUR_THIRD_VM_HERE",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password",
        "description": "Third test VM"
      }
    ],
    
    "Firewall_VMs": [
      {
        "name": "pfSense_FW1",
        "path": "PUT_PATH_TO_PFSENSE_HERE",
        "type": "Firewall",
        "ram_mb": 1024,
        "cpus": 1,
        "username": "admin",
        "password": "pfsense",
        "description": "pfSense firewall"
      },
      {
        "name": "pfSense_FW2",
        "path": "PUT_PATH_TO_SECOND_PFSENSE_HERE",
        "type": "Firewall",
        "ram_mb": 1024,
        "cpus": 1,
        "username": "admin",
        "password": "pfsense",
        "description": "Second pfSense (if you have it)"
      }
    ]
  }
}
```

### Step 4: If you only have ONE pfSense

If you only have one pfSense VM, just remove the second firewall:

```json
"Firewall_VMs": [
  {
    "name": "pfSense_FW1",
    "path": "C:\\Users\\Sachin\\Downloads\\pfsense.ova",
    "type": "Firewall",
    "ram_mb": 1024,
    "cpus": 1,
    "username": "admin",
    "password": "pfsense",
    "description": "pfSense firewall"
  }
]
```

### Step 5: Update usernames and passwords

Replace these with the actual SSH credentials for your VMs:

```json
"username": "user",     ← Your VM's SSH username
"password": "password", ← Your VM's SSH password
```

**Common defaults:**
- Debian: username `user` or `debian`, password whatever you set
- Ubuntu: username `ubuntu` or `user`
- pfSense: username `admin`, password `pfsense`

---

## Real Example (Based on What You Probably Have)

Let's say you have:
- 2 Debian VMs (the ones Rakesh sent you)
- 1 pfSense you'll download

Your `vm_inventory.json` should look like:

```json
{
  "vm_directory": "C:\\Users\\Sachin\\VirtualBox VMs",
  
  "available_vms": {
    "IT_VMs": [
      {
        "name": "Debian_VM1",
        "path": "C:\\Users\\Sachin\\VirtualBox VMs\\Debian1\\Debian1.ova",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password",
        "description": "First Debian VM from Rakesh"
      },
      {
        "name": "Debian_VM2",
        "path": "C:\\Users\\Sachin\\VirtualBox VMs\\Debian2\\Debian2.ova",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password",
        "description": "Second Debian VM from Rakesh"
      },
      {
        "name": "Ubuntu_Test",
        "path": "C:\\Users\\Sachin\\Downloads\\ubuntu-vm.ova",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "ubuntu",
        "password": "ubuntu",
        "description": "Ubuntu test VM"
      }
    ],
    
    "Firewall_VMs": [
      {
        "name": "pfSense",
        "path": "C:\\Users\\Sachin\\Downloads\\pfsense.ova",
        "type": "Firewall",
        "ram_mb": 1024,
        "cpus": 1,
        "username": "admin",
        "password": "pfsense",
        "description": "pfSense firewall"
      }
    ]
  }
}
```

---

## What If You Don't Have the VMs Yet?

### For Testing WITHOUT actual VMs:

You can still test the **interface and logic** by:

1. **Comment out the import/deploy parts** temporarily
2. **Just test the selection flow**

Create a `vm_inventory_test.json`:

```json
{
  "vm_directory": "",
  
  "available_vms": {
    "IT_VMs": [
      {
        "name": "TestVM1",
        "path": "",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password",
        "description": "Test VM 1"
      },
      {
        "name": "TestVM2",
        "path": "",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password",
        "description": "Test VM 2"
      },
      {
        "name": "TestVM3",
        "path": "",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password",
        "description": "Test VM 3"
      }
    ],
    
    "Firewall_VMs": [
      {
        "name": "TestFirewall1",
        "path": "",
        "type": "Firewall",
        "ram_mb": 1024,
        "cpus": 1,
        "username": "admin",
        "password": "admin",
        "description": "Test Firewall 1"
      },
      {
        "name": "TestFirewall2",
        "path": "",
        "type": "Firewall",
        "ram_mb": 1024,
        "cpus": 1,
        "username": "admin",
        "password": "admin",
        "description": "Test Firewall 2"
      }
    ]
  }
}
```

This way you can test the **selection interface** and see what configuration it generates, even without deploying real VMs.

---

## How to Run with Your Config File

**Method 1: Modify network_builder.py**

Around line 60 in `network_builder.py`, change:

```python
def load_vm_inventory(self, config_file=None):
```

To:

```python
def load_vm_inventory(self, config_file="vm_inventory.json"):
```

This makes it automatically load your config.

**Method 2: Pass config file as argument**

Modify the `main()` function at the bottom:

```python
def main():
    """Entry point"""
    builder = NetworkBuilder()
    
    # Load from your custom config
    if not builder.load_vm_inventory("vm_inventory.json"):
        print("Failed to load inventory")
        return
    
    try:
        builder.run()
    except KeyboardInterrupt:
        print("\n\n⚠ Cancelled by user")
```

---

## Demo Scenario Example

For your Saturday demo, here's a realistic scenario:

**Setup:**
- 2 VMs in IT subnet (192.168.40.x)
- 1 VM in OT subnet (192.168.60.x)
- 1 pfSense connecting them

**User selections:**
```
How many subnets? 2

Subnet 1: IT_Subnet (192.168.40.0/24)
Subnet 2: OT_Subnet (192.168.60.0/24)

IT_Subnet VMs: VM1_Debian, VM2_Ubuntu
OT_Subnet VMs: VM3_CentOS

Firewall: pfSense_FW1
  WAN → IT_Subnet
  LAN → OT_Subnet

Deploy? Yes
```

**Result:**
```
[VM1_Debian]───┐
[VM2_Ubuntu]───┼──[192.168.40.x]──[pfSense WAN]
                                        │
                                  [pfSense LAN]──[192.168.60.x]──[VM3_CentOS]
```

---

## Adding More VMs Later

When you get more VMs from Rakesh, just add them to `vm_inventory.json`:

```json
"OT_VMs": [
  {
    "name": "PLC_Simulator",
    "path": "C:\\VMs\\OT\\plc_sim.ova",
    "type": "OT",
    "ram_mb": 4096,
    "cpus": 4,
    "username": "operator",
    "password": "password",
    "description": "Industrial PLC simulator"
  },
  {
    "name": "SCADA_System",
    "path": "C:\\VMs\\OT\\scada.ova",
    "type": "OT",
    "ram_mb": 8192,
    "cpus": 4,
    "username": "scada",
    "password": "password",
    "description": "SCADA monitoring system"
  }
],

"Scanner_VMs": [
  {
    "name": "Wazuh_Scanner",
    "path": "C:\\VMs\\Scanners\\wazuh.ova",
    "type": "Scanner",
    "ram_mb": 4096,
    "cpus": 2,
    "username": "wazuh",
    "password": "wazuh",
    "description": "Wazuh security scanner"
  }
]
```

The script will automatically show them in the selection menu!

---

## Quick Checklist

Before running the demo:

- [ ] Update all `path` fields with actual file paths
- [ ] Update `username` and `password` for each VM
- [ ] Test that paths exist: `dir "C:\path\to\your\vm.ova"`
- [ ] Ensure VirtualBox is installed
- [ ] Ensure Python + paramiko are installed
- [ ] Run a dry-run without deploying first

---

## Next Steps

1. **Create your `vm_inventory.json`** with your actual VM paths
2. **Test the selection interface** without deployment
3. **Deploy to 1 VM first** to test import
4. **Then deploy full setup** (2 VMs + firewall)
5. **Show to Rakesh** on Saturday! 🎉
