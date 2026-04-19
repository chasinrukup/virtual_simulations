# Network Simulation Orchestrator

## What This Project Is

A command-line tool that automates the creation and management of virtual network labs using VirtualBox. Instead of manually creating VMs, configuring network adapters, and wiring everything together through VirtualBox's GUI, this tool does it all through interactive terminal prompts.

The core use case: **build a network where VMs communicate through a firewall**, simulating real-world segmented networks (corporate IT/OT environments, security labs, penetration testing setups).

```
[VM1] ──── Subnet_A ──── [Firewall] ──── Subnet_B ──── [VM2]
```

VM1 cannot talk to VM2 directly. All traffic must pass through the firewall, which decides what is allowed or blocked.

---

## How It Works (The Big Picture)

### What Happens When You Run the Tool

1. **Scans your directory** for VM images (ISOs, OVAs, VirtualBox VM folders)
2. **You classify each image** as "endpoint" (regular VM) or "firewall" (once, saved permanently)
3. **You choose a mode:**
   - **Prebuilt** — picks from 3 ready-made subnets, you just assign VMs
   - **Custom** — you configure everything: subnet IPs, DHCP, adapter count
4. **You assign VMs to subnets** and pick which one is the firewall
5. **The tool deploys everything** to VirtualBox:
   - Creates host-only network adapters (virtual switches)
   - Configures DHCP on each adapter
   - Creates/imports VMs
   - Plugs each VM's network cable into the right adapter
   - Wires the firewall to both subnets
   - Starts everything (firewall first, then endpoints)

### What It Creates in VirtualBox

For a simple 2-subnet lab:

```
Your Windows Host
├── Host-Only Adapter #2 (192.168.30.1) ← Subnet_A
│   ├── DHCP Server (assigns 192.168.30.100 - .200)
│   ├── VM1 (NIC1 plugged in here)
│   └── Firewall (NIC1 / WAN plugged in here)
│
└── Host-Only Adapter #3 (192.168.40.1) ← Subnet_B
    ├── DHCP Server (assigns 192.168.40.100 - .200)
    ├── VM2 (NIC1 plugged in here)
    └── Firewall (NIC2 / LAN plugged in here)
```

The firewall has two NICs — one on each subnet. It routes traffic between them.

---

## Three Ways to Use It

### 1. `cli.py` — Main Tool (Recommended)

```
python cli.py
```

The full-featured interactive CLI. Supports:
- Prebuilt and Custom modes
- All image types (ISO, OVA, VBox)
- Config save/load
- Validation before deployment
- Stop/delete management

**Best for:** Building labs from scratch using ISO installers or pre-built appliance files.

### 2. `lab_existing.py` — Quick Lab from Existing VMs

```
python lab_existing.py
```

A lightweight standalone tool that works with VMs already registered in VirtualBox. No new VMs are created — it just:
- Lists your existing VMs
- Lets you tag them as endpoint/firewall
- Wires their NICs to subnets
- Starts them

**Best for:** When you already have VMs installed and just need to wire up the network.

### 3. `network_builder.py` — Legacy Builder

```
python network_builder.py
```

The original interactive builder. Still works but uses internal networks (intnet) instead of host-only adapters.

**Best for:** Backward compatibility with older configurations.

---

## Project Structure

```
virtual_simulations/
│
│── Entry Points ──────────────────────────────────────
├── cli.py                 Main interactive CLI
├── lab_existing.py        Quick lab from existing VMs
├── network_builder.py     Legacy builder
├── test_config.py         Pre-deployment checks
│
│── Data Models ───────────────────────────────────────
├── models.py              Subnet, VMConfig, FirewallConfig, LabConfig, etc.
│
│── VirtualBox Interface ──────────────────────────────
├── vbox.py                Low-level VBoxManage command runner
├── vm_manager.py          VM lifecycle (create, start, stop, delete, import)
├── adapter_manager.py     Host-only adapter CRUD + DHCP
├── vm_controller.py       Legacy VBoxManage wrapper class
│
│── Business Logic ────────────────────────────────────
├── network_manager.py     Creates subnets (adapter + DHCP wiring)
├── firewall_manager.py    Assigns firewall WAN/LAN interfaces
├── deployer.py            Orchestrates full lab deployment
├── validator.py           Validates config before deployment
├── prebuilt.py            Pre-configured subnet templates
│
│── Persistence ───────────────────────────────────────
├── config_store.py        Save/load configs, scan for images
├── iso_roles.json         Saved image classifications (endpoint/firewall)
├── vm_inventory.json      Image inventory and default hardware configs
├── configs/               Saved lab configuration files
│   └── lab_config.json
│
│── Utilities ─────────────────────────────────────────
├── ssh_manager.py         SSH into VMs for post-deploy configuration
├── logger.py              File + console logging
├── lab_orchestrator.log   Runtime log file
│
│── VM Images ─────────────────────────────────────────
├── *.iso                  ISO installer images
├── kali-linux-.../        VirtualBox VM folder (pre-built)
├── PHP/.../**.ova         OVA appliance files (in subfolders)
├── CVE-2011-2523/.../     OVA appliance files (in subfolders)
│
│── Documentation ─────────────────────────────────────
├── PROJECT_DOCUMENTATION.md   This file
├── QUICK_REFERENCE.md         Quick setup cheat sheet
└── CUSTOMIZATION_GUIDE.md     Detailed customization help
```

---

## What Each Module Does

### models.py — Data Structures

Defines all the data types used throughout the project as Python dataclasses:

| Class | Purpose | Key Fields |
|-------|---------|------------|
| `Subnet` | A network segment mapped to one adapter | name, network (192.168.30.0/24), gateway_ip, dhcp config |
| `Adapter` | A VirtualBox host-only network adapter | name (VBox-assigned), IP, netmask |
| `DHCPConfig` | DHCP server settings for an adapter | server_ip, lower_ip, upper_ip, enabled |
| `VMConfig` | Everything needed to create/configure a VM | name, RAM, CPUs, disk, ISO path, image_type, role, subnets |
| `FirewallConfig` | Which subnets the firewall connects | vm_name, wan_subnet, lan_subnets |
| `LabConfig` | Complete deployable lab definition | list of subnets + VMs + firewall config |
| `ImageInfo` | Metadata about a discovered VM image | filename, path, size, OS type, image_type (iso/ova/vbox), role |

Also contains `OS_TYPES` — a mapping from keywords (debian, ubuntu, kali, netgate) to VirtualBox OS type identifiers (Debian_64, Ubuntu_64, FreeBSD_64).

### vbox.py — VirtualBox Command Runner

The single point of contact for all VBoxManage CLI calls. Every other module goes through this instead of calling subprocess directly.

- `check_vbox()` — Verifies VBoxManage.exe exists
- `run(args)` — Executes a command, logs it, returns stdout or None on failure

Hardcoded path: `C:\Program Files\Oracle\VirtualBox\VBoxManage.exe`

### adapter_manager.py — Network Adapter Management

Manages VirtualBox host-only adapters (the virtual switches that form each subnet):

- `list_adapters()` — Queries VirtualBox for all existing host-only adapters
- `find_adapter_by_ip(ip)` — Finds an adapter with a specific IP (to reuse instead of creating duplicates)
- `create_adapter(ip, netmask)` — Creates a new adapter or reuses an existing one with that IP
- `configure_dhcp(...)` — Sets up a DHCP server on the adapter so VMs get IPs automatically
- `disable_dhcp(...)` — Removes a DHCP server

**Why host-only adapters?** They create isolated virtual networks. VMs on the same adapter can see each other. VMs on different adapters cannot — unless a firewall routes between them.

### vm_manager.py — VM Lifecycle

Handles everything about VMs themselves:

- `create_vm(name, ostype, ram, cpus, disk)` — Creates a brand new empty VM with a virtual hard disk
- `attach_iso(vm_name, iso_path)` — Mounts an ISO as a bootable DVD
- `import_ova(ova_path, name)` — Imports a pre-built OVA appliance (already has OS installed)
- `register_vbox(vbox_path, name)` — Registers an existing VirtualBox VM folder
- `setup_image(image_info, vm_name)` — Auto-detects image type and does the right thing
- `configure_nic(vm_name, adapter_num, adapter_name)` — Plugs a VM's NIC into a host-only adapter
- `start_vm(name, headless)` — Boots the VM (GUI window or headless background)
- `stop_vm(name, force)` — Shuts down (graceful ACPI or force poweroff)
- `delete_vm(name)` — Unregisters and deletes VM and all its files

**Three image types explained:**

| Type | File Extension | What Happens | Ready to Use? |
|------|---------------|--------------|---------------|
| ISO | `.iso` | Creates new empty VM, mounts ISO as DVD | No — you must install the OS |
| OVA | `.ova` | Imports pre-built appliance | Yes — OS already installed |
| VBox | `.vbox` (folder) | Registers existing VM with VirtualBox | Yes — OS already installed |

### network_manager.py — Subnet Creation

Bridges the gap between the abstract "Subnet" concept and the actual VirtualBox adapters:

- `create_subnet(subnet)` — Creates a host-only adapter with the subnet's IP, configures DHCP, stores the adapter name back into the Subnet object
- `assign_vm_to_subnet(vm_name, subnet, adapter_num)` — Connects a VM's NIC to a subnet's adapter
- `destroy_subnet(subnet)` — Removes the adapter and its DHCP server

### firewall_manager.py — Firewall Wiring

Configures the firewall VM's network interfaces:

- `configure_firewall(fw_config, subnets)` — Assigns NIC 1 to the WAN subnet and NIC 2+ to LAN subnets, enables promiscuous mode on all interfaces

The firewall is just a regular VM with multiple NICs. What makes it a "firewall" is that it has one NIC on each subnet and runs routing/filtering software (like pfSense) inside.

### validator.py — Pre-deployment Checks

Runs before deployment to catch configuration errors:

| Validation | What It Checks |
|-----------|---------------|
| No duplicate adapters | Each subnet uses a unique adapter |
| DHCP range valid | Lower IP < upper IP, both in same /24 as gateway |
| Firewall has 2+ subnets | A firewall with 1 subnet has nothing to route between |
| WAN and LAN are different | Can't use the same subnet for both |
| VM NIC limit | VirtualBox supports max 4 NICs per VM |
| No subnet overlap | Two subnets can't share the same network prefix |

All validators return a list of error strings. Empty list means valid.

### deployer.py — Deployment Orchestrator

The main engine that takes a validated LabConfig and builds everything:

```
Step 1: Validate config           → Catches errors before touching VirtualBox
Step 2: Create subnets            → Host-only adapters + DHCP servers
Step 3: Create/import VMs         → Based on image type (ISO/OVA/VBox)
Step 4: Wire VMs to subnets       → Connect each VM's NICs to the right adapters
Step 5: Configure firewall        → WAN on one subnet, LAN on the other(s)
Step 6: Start VMs                 → Firewall boots first, then endpoints
```

Also provides `show_lab_status()`, `stop_all()`, and `delete_all()`.

### prebuilt.py — Fast Setup Templates

Contains 3 pre-configured subnets ready to use:

| Subnet | Network | Gateway | DHCP Range |
|--------|---------|---------|------------|
| Subnet_A | 192.168.30.0/24 | 192.168.30.1 | .100 - .200 |
| Subnet_B | 192.168.40.0/24 | 192.168.40.1 | .100 - .200 |
| Subnet_C | 192.168.50.0/24 | 192.168.50.1 | .100 - .200 |

In Prebuilt mode, the user picks 1-3 subnets, assigns VMs, and deploys. No manual IP or DHCP configuration needed.

### config_store.py — Persistence

Handles saving and loading:

- **ISO/image roles** (`iso_roles.json`) — Remembers which images are "endpoint" vs "firewall" so you're not asked every time
- **Image scanning** — Recursively walks directories finding `.iso`, `.ova`, and `.vbox` files
- **Lab configs** — Serializes/deserializes LabConfig to JSON for saving and reloading labs

### logger.py — Logging

Dual output logging:
- **Console:** INFO level and above (what the user sees)
- **File** (`lab_orchestrator.log`): DEBUG level (full VBoxManage commands and outputs for troubleshooting)

### ssh_manager.py — Post-Deploy SSH

Optional module for SSH-ing into VMs after they boot to configure networking:
- Connect with username/password
- Run commands remotely
- Configure static IPs on Linux VMs

Requires `pip install paramiko`. The rest of the tool works without it.

### cli.py — Main Interactive Interface

The primary user-facing module. Provides:

- **ImageManager class** — Scans images, tracks which ones are used (prevents picking the same image twice), filters by role
- **Prebuilt mode** — Fast path: pick subnets (1-3), assign VMs, optional firewall
- **Custom mode** — Full control: define subnets, IPs, DHCP ranges, assign VMs to multiple subnets, configure firewall routing
- **Review screen** — Shows full config + ASCII topology diagram + validation results
- **Management** — Stop VMs, delete VMs, check status, save/load configs

### lab_existing.py — Existing VM Tool

A standalone script (no dependencies on other project modules) for when VMs are already registered in VirtualBox:

1. Reads VMs directly from VirtualBox's registry
2. User tags each as endpoint/firewall/skip
3. Creates or reuses host-only adapters for subnets
4. Wires NICs and starts VMs

No ISO mounting, no VM creation — just networking and startup.

---

## Key Concepts

### Subnets

A subnet is a separate network segment. VMs on the same subnet can communicate directly. VMs on different subnets cannot — they need a router/firewall to pass traffic between them.

Each subnet in this tool maps to one VirtualBox host-only adapter with its own IP range and DHCP server.

### Host-Only Adapters

Virtual network switches created by VirtualBox on your host machine. Each one:
- Gets its own IP address (acts as the gateway)
- Can run a DHCP server (auto-assigns IPs to VMs)
- Is completely isolated from other adapters

### Firewall (Multi-Homed VM)

A VM with 2+ NICs, each connected to a different subnet. It runs routing/firewall software (like pfSense) that decides what traffic can pass between subnets.

- **WAN interface** — The "outside" subnet
- **LAN interface(s)** — The "inside" subnet(s)

### Image Types

| Type | What It Is | Use Case |
|------|-----------|----------|
| ISO | OS installer disc image | When you need a fresh install |
| OVA | Pre-built VM appliance | Ready-to-run VMs from the internet |
| VBox | Existing VirtualBox VM folder | VMs you've already set up |

### Role Classification

Every image is tagged as either "endpoint" (regular VM) or "firewall". This is saved to `iso_roles.json` so you only classify once. The tool shows the right images at the right time — firewall ISOs when picking a firewall, endpoint ISOs when picking endpoints.

---

## Deployment Flow (Step by Step)

```
User runs: python cli.py

1. SCAN
   └── Recursively finds all .iso, .ova, .vbox files
   └── Loads saved role classifications
   └── Asks about any new/unclassified images

2. MODE SELECTION
   ├── Prebuilt: 3 ready subnets, just pick VMs
   └── Custom: configure everything manually

3. CONFIGURATION
   ├── Define subnets (or use prebuilt ones)
   ├── Pick images for each VM
   ├── Set hardware (RAM, CPUs, disk)
   ├── Assign VMs to subnets
   └── Configure firewall (WAN/LAN subnets)

4. REVIEW
   ├── Show full config summary
   ├── ASCII topology diagram
   └── Run validation checks

5. DEPLOY
   ├── Create host-only adapters + DHCP servers
   ├── Create VMs (or import OVAs / register VBox VMs)
   ├── Connect VM NICs to subnet adapters
   ├── Wire firewall to WAN and LAN subnets
   └── Start all VMs (firewall first)

6. MANAGE
   ├── Show status (running/off)
   ├── Stop VMs (individual or all)
   └── Delete VMs (individual or all)
```

---

## Requirements

- **VirtualBox 7.x** installed at `C:\Program Files\Oracle\VirtualBox\`
- **Python 3.6+**
- **paramiko** (optional, only needed for SSH features): `pip install paramiko`
- **Windows 10/11**

---

## Quick Start

### Fastest path (existing VMs):
```bash
python lab_existing.py
# Pick VMs → assign subnets → start
```

### Full lab from images:
```bash
python cli.py
# Scan images → Prebuilt mode → assign VMs → deploy
```

### Verify setup first:
```bash
python test_config.py
# Checks VirtualBox, Python, dependencies
```
