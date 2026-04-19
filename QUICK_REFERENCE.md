# Quick Reference - What to Change for Your Demo

## THE ONE FILE YOU NEED TO EDIT: `vm_inventory.json`

### Step-by-Step Changes:

#### 1. Find Your VM Files
On Windows, your VMs are probably in one of these locations:
```
C:\Users\YourName\VirtualBox VMs\
C:\Users\YourName\Downloads\
D:\VMs\
```

#### 2. Get the Full Path
- Right-click on the VM file (`.ova` or `.ovf`)
- Properties → Copy the path
- Example: `C:\Users\Sachin\VirtualBox VMs\Debian1.ova`

#### 3. Edit vm_inventory.json

**Replace these 5 things:**

```json
{
  "vm_directory": "C:\\VMs\\OVAs",  ← 1. YOUR VM FOLDER

  "available_vms": {
    "IT_VMs": [
      {
        "name": "VM1_Debian",
        "path": "C:\\VMs\\OVAs\\debian_vm1.ova",  ← 2. PATH TO VM1
        "username": "user",      ← 3. SSH USERNAME
        "password": "password",  ← 4. SSH PASSWORD
      },
      {
        "name": "VM2_Ubuntu",
        "path": "C:\\VMs\\OVAs\\ubuntu_vm.ova",  ← 5. PATH TO VM2
        "username": "user",
        "password": "password",
      },
      // ... VM3 similar
    ],
    
    "Firewall_VMs": [
      {
        "name": "pfSense_FW1",
        "path": "C:\\VMs\\OVAs\\pfsense.ova",  ← PATH TO PFSENSE
        "username": "admin",
        "password": "pfsense",
      }
    ]
  }
}
```

**IMPORTANT:** Use double backslashes `\\` in Windows paths!
- ✓ Correct: `"C:\\Users\\Sachin\\vm.ova"`
- ✗ Wrong: `"C:\Users\Sachin\vm.ova"`

---

## Testing Your Configuration (Before Demo Day)

### Test 1: Check Configuration
```bash
python test_config.py
```

This shows:
- ✓ What VMs were loaded
- ❌ Which paths are invalid
- ✓ If prerequisites are installed

### Test 2: Run the Builder
```bash
python network_builder.py
```

Follow the prompts to test the interface.

---

## Minimal Demo Setup (2 VMs + 1 Firewall)

For Saturday's demo, you only need:

**vm_inventory.json:**
```json
{
  "available_vms": {
    "IT_VMs": [
      {
        "name": "VM1",
        "path": "PATH_TO_YOUR_FIRST_VM.ova",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password"
      },
      {
        "name": "VM2",
        "path": "PATH_TO_YOUR_SECOND_VM.ova",
        "type": "IT",
        "ram_mb": 2048,
        "cpus": 2,
        "username": "user",
        "password": "password"
      }
    ],
    
    "Firewall_VMs": [
      {
        "name": "pfSense",
        "path": "PATH_TO_PFSENSE.ova",
        "type": "Firewall",
        "ram_mb": 1024,
        "cpus": 1,
        "username": "admin",
        "password": "pfsense"
      }
    ]
  }
}
```

**Demo Flow:**
```
$ python network_builder.py

How many subnets? 2
Subnet 1 name: IT_Subnet
Subnet 2 name: OT_Subnet

Assign VMs to IT_Subnet: 1
Assign VMs to OT_Subnet: 2

Add firewall? y
Firewall VM: 1 (pfSense)
WAN subnet: IT_Subnet
LAN subnet: OT_Subnet

Deploy? y
```

**Result:**
```
[VM1] ──[192.168.40.x]── [pfSense WAN]
                              │
                         [pfSense LAN] ──[192.168.60.x]── [VM2]
```

---

## Common Issues & Fixes

### ❌ "File not found"
**Fix:** Check path in vm_inventory.json
- Make sure file exists at that location
- Use double backslashes: `C:\\path\\to\\vm.ova`

### ❌ "Module 'paramiko' not found"
**Fix:** Install it
```bash
pip install paramiko
```

### ❌ "VBoxManage not recognized"
**Fix:** Add VirtualBox to PATH or use full path
```
"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
```

### ❌ VM import fails
**Fix:** Make sure:
- VirtualBox is installed
- VM file is valid OVA/OVF
- No VM with same name already exists

---

## Files You'll Use

### Required Files:
1. **vm_inventory.json** - Your VM configuration (EDIT THIS!)
2. **network_builder.py** - Main program (don't edit)
3. **vm_controller.py** - VirtualBox wrapper (don't edit)
4. **ssh_manager.py** - SSH functions (don't edit)

### Testing Files:
5. **test_config.py** - Test your configuration
6. **CUSTOMIZATION_GUIDE.md** - Detailed help (this file)

---

## Before Saturday Demo

- [ ] Download pfSense (if you don't have it)
- [ ] Update vm_inventory.json with real paths
- [ ] Run `python test_config.py` to verify
- [ ] Test deployment with 1 VM first
- [ ] Then test full setup (2 VMs + firewall)
- [ ] Document what works and what doesn't

---

## Quick Commands

**Test configuration:**
```bash
python test_config.py
```

**Run the builder:**
```bash
python network_builder.py
```

**Check VirtualBox VMs:**
```bash
VBoxManage list vms
```

**Check VirtualBox networks:**
```bash
VBoxManage list hostonlyifs
```

---

## What Rakesh Wants to See

✓ Interactive selection (not hardcoded)
✓ User chooses VMs from a list
✓ User defines network topology
✓ System deploys automatically
✓ Command-line interface (no web UI yet)

Good luck! 🚀
