# Virtual Network Simulation Lab

A web-based network simulation platform that spins up real VirtualBox VMs into isolated virtual networks directly from your browser. Deploy pre-built security scenarios or build custom multi-subnet labs with a point-and-click wizard — then SSH into any VM right from the UI.

## What It Does

- **5 prebuilt scenarios** — firewall basics, flat vulnerability lab, segmented attack/defense, multi-zone network, enterprise network
- **Custom lab builder** — wizard to define subnets (WAN/LAN/DMZ/MGMT/DEV) and place VMs on them
- **In-browser SSH terminal** — click any running VM to open a shell session
- **Kali desktop** — click the Kali VM to open a full GUI via noVNC
- **Background ping test** — after deploying a prebuilt scenario, automatically SSHs into each VM and pings all others, logging results live
- **One-click teardown** — stop or delete the entire lab from the UI

---

## Requirements

| Requirement | Notes |
|---|---|
| **Windows 10/11** (64-bit) | Host OS — tested on Windows 10 Pro |
| **VirtualBox 7.x** | Must be installed and `VBoxManage` on PATH |
| **Python 3.10+** | For the Flask web server |
| **~50 GB free disk** | For VM images |
| **16 GB RAM** | Recommended; 8 GB minimum for small scenarios |

### Python packages

```
pip install flask flask-sock paramiko
```

---

## VM Images (Required)

The app looks for VM images in a sibling folder called `virtual_simulations` (one level up from this repo). The expected layout is:

```
parent-folder/
├── virtual_simulations/          ← put images here
│   ├── emyers_unbuntu_vsftpd.ova
│   ├── pfSense_export.ova
│   ├── emyers-vulnhu-php/        ← registered VirtualBox VM (clone source)
│   └── kali-linux-2025.4-virtualbox-amd64/  ← registered VirtualBox VM
└── virtual_simulations_web/      ← this repo
```

### Changing the images path

Edit `web_config.py`:

```python
IMAGES_DIR = r"C:\path\to\your\images"
```

### Required images

| File / Folder | Used by | Notes |
|---|---|---|
| `emyers_unbuntu_vsftpd.ova` | All scenarios | Ubuntu 18 with vsftpd vulnerable service |
| `pfSense_export.ova` | Scenarios 1, 3, 4, 5 | Pre-configured pfSense firewall |
| `emyers-vulnhu-php` | Scenarios 1, 2, 4, 5 | Debian VM with PHP-CGI vuln (CVE-2012-1823) — must be registered in VirtualBox |
| `kali-linux-2025.4-virtualbox-amd64` | Scenarios 3, 5 | Kali Linux with VNC enabled — must be registered in VirtualBox |

### Registering existing VMs

If you already have a `.vbox` file, register it with VirtualBox before running:

```powershell
VBoxManage registervm "C:\path\to\kali-linux-2025.4-virtualbox-amd64\kali-linux-2025.4-virtualbox-amd64.vbox"
VBoxManage registervm "C:\path\to\emyers-vulnhu-php\emyers-vulnhu-php.vbox"
```

---

## VirtualBox Network Setup

The app uses **VirtualBox host-only adapters** to create isolated subnets. You need one adapter per subnet. The app creates them automatically on first deploy, but you can also pre-create them:

| Subnet | Network | VirtualBox Adapter |
|---|---|---|
| WAN | 192.168.30.0/24 | Host-Only Adapter #3 |
| LAN | 192.168.40.0/24 | Host-Only Adapter #4 |
| DMZ | 192.168.50.0/24 | Host-Only Adapter #5 |
| MGMT | 192.168.60.0/24 | Host-Only Adapter #6 |
| DEV | 192.168.70.0/24 | Host-Only Adapter #7 |

---

## Installation

```powershell
# 1. Clone the repo
git clone https://github.com/chasinrukup/virtual_simulations_web.git
cd virtual_simulations_web

# 2. Install Python dependencies
pip install flask flask-sock paramiko

# 3. Verify VBoxManage is accessible
VBoxManage --version

# 4. Place VM images in the images folder (see above)

# 5. Start the server
python app.py
```

The web UI is at **http://localhost:8080**

---

## Usage

### Deploying a prebuilt scenario

1. Open http://localhost:8080
2. Click a scenario card in the left sidebar
3. Review the description and VM list in the modal
4. Click **Deploy** — VMs import, NICs wire up, VMs start (takes 1–3 minutes)
5. Watch the **Deployment Log** at the bottom for progress
6. Once all VMs show green "running" badges, click any VM name to SSH in

### SSH into a VM

- Click the VM name in the **Network Topology** or **VM Status** panel
- A dialog shows the pre-filled IP, username, and password
- Click **Open Terminal** — an xterm.js shell opens in the browser

### Kali desktop (noVNC)

- Click the **Kali** VM — a "Open Desktop" button appears instead of SSH
- Requires VNC to be running inside Kali:
  ```bash
  tightvncserver :1 -geometry 1280x800 -depth 24
  ```
- The app proxies the VNC connection through a WebSocket

### Ping test (prebuilt mode only)

After a prebuilt lab finishes deploying, the **Ping All VMs** button activates. Click it (or wait — it auto-fires 90 seconds after the lab reaches "running") to SSH into each endpoint VM and ping all others. Results stream into the Deployment Log.

### Stop / delete a lab

- **Stop All** — ACPI shutdown all VMs (preserves disk state)
- **Delete Lab** — powers off and unregisters all VMs (cloned VMs are deleted; `.vbox` VMs like Kali are only unregistered, files stay)

### Build a custom lab

1. Click **Build Custom Lab** in the sidebar
2. **Step 1** — add subnets (WAN, LAN, DMZ, etc.)
3. **Step 2** — add VMs, assign each to a subnet; choose "firewall" role to bridge subnets
4. **Step 3** — name the lab and click **Deploy**

---

## Default VM Credentials

| VM Image | Username | Password |
|---|---|---|
| `emyers_unbuntu_vsftpd` | `john` | `admin` |
| `emyers-vulnhu-php` | `john` | `admin` |
| Kali Linux | `kali` | `kali` |
| pfSense | `admin` | `pfsense` (web UI) |

---

## Prebuilt Scenarios

| # | Name | Subnets | VMs | Purpose |
|---|---|---|---|---|
| 1 | Firewall Basics | WAN + LAN | vsftpd, PHP-CGI, pfSense | Learn how a firewall segments two subnets |
| 2 | Flat Vulnerability Lab | LAN | vsftpd, PHP-CGI | Scanning/exploitation without a firewall |
| 3 | Segmented Attack/Defense | WAN + LAN | Kali, vsftpd, pfSense | Attacker on WAN vs. defender behind pfSense |
| 4 | Multi-Zone Network | WAN + LAN + DMZ | vsftpd, PHP-CGI, FW1, FW2 | Two firewalls, three isolated zones |
| 5 | Enterprise Network | WAN + LAN + DMZ | Kali, vsftpd, PHP-CGI, pfSense | One firewall managing three zones |

---

## Project Structure

```
virtual_simulations_web/
├── app.py                  # Flask server — all API routes, SSH sessions, state
├── web_config.py           # IMAGES_DIR and port settings
├── deployer.py             # Orchestrates VM import → NIC wiring → start
├── prebuilt.py             # Scenario definitions (subnets, VMs, firewalls)
├── vm_manager.py           # VBoxManage wrappers (create, clone, start, delete)
├── network_manager.py      # Host-only adapter management + DHCP
├── firewall_manager.py     # pfSense NIC assignment
├── adapter_manager.py      # Low-level VirtualBox adapter helpers
├── validator.py            # Config validation before deploy
├── models.py               # LabConfig, Subnet, VMConfig, FirewallConfig dataclasses
├── logger.py               # Shared logger
├── vbox.py                 # VBoxManage subprocess wrapper
├── templates/
│   └── index.html          # Single-page UI
└── static/
    ├── app.js              # All frontend JS (polling, SSH terminal, wizard)
    └── style.css           # UI styles
```

---

## Troubleshooting

**VMs fail to import — disk full**
- Each OVA/clone needs 5–20 GB. Check `VBoxManage list hdds` for orphaned disks.
- Delete stale VMs: `VBoxManage unregistervm <name> --delete`

**VM gets no IP / SSH can't connect**
- The app discovers IPs via ARP cache first, then reads VirtualBox DHCP lease files in `~/.VirtualBox/*.leases`.
- Wait 30–60 seconds after the VM shows "running" for DHCP to complete.

**Cross-subnet ping fails through pfSense**
- pfSense blocks WAN→LAN by default. This is intentional in Scenario 1 (Firewall Basics) — it demonstrates firewall segmentation.
- To allow traffic, access the pfSense web UI at `https://<pfsense-lan-ip>` and add a WAN pass rule.

**SSH "Authentication failed" for PHP-CGI VM**
- The `emyers-vulnhu-php` machine is a deliberately vulnerable target. If SSH credentials are unknown, the ping test will skip it and log the failure.

**Kali desktop shows blank / noVNC error**
- VNC must be running inside Kali before clicking "Open Desktop".
- Inside Kali: `tightvncserver :1 -geometry 1280x800 -depth 24`
- Default VNC password: `kali`

**`flask-sock` not found**
- `pip install flask-sock` — required for the SSH WebSocket proxy.

---

## Architecture Notes

- All VM state lives in `_state` (in-memory) — restarting the server loses awareness of running VMs. Running VMs continue in VirtualBox; just redeploy to reconnect.
- SSH sessions use paramiko PTY channels, buffered server-side, polled by the frontend every 100 ms.
- IP discovery: ARP cache → VirtualBox DHCP lease XML → ping-sweep + ARP.
- The app writes no files during operation except `lab_orchestrator.log`.
