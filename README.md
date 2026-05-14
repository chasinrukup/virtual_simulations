# Virtual Network Simulation Lab

A web-based network simulation platform that spins up real VirtualBox VMs into isolated virtual networks directly from your browser. Deploy pre-built security scenarios or build custom multi-subnet labs with a point-and-click wizard — then SSH into any VM right from the UI.

## What It Does

- **5 prebuilt scenarios** — firewall basics, flat vulnerability lab, segmented attack/defense, multi-zone network, enterprise network
- **Custom lab builder** — wizard to define subnets (WAN/LAN/DMZ/MGMT/DEV) and place VMs on them
- **In-browser SSH terminal** — click any running VM to open a shell session
- **Kali desktop** — click the Kali VM to open a full GUI via noVNC
- **Background ping test** — SSHs into each VM and pings all others, logging results live
- **One-click teardown** — stop or delete the entire lab from the UI

---

## System Requirements

| Requirement | Version | Notes |
|---|---|---|
| **Windows** | 10 or 11 (64-bit) | Host OS — tested on Windows 10 Pro |
| **VirtualBox** | 7.x | Download from virtualbox.org |
| **Python** | 3.10 or newer | Download from python.org |
| **Free disk** | ~50 GB | For VM images |
| **RAM** | 16 GB recommended | 8 GB minimum for small scenarios |

---

## Step 1 — Install VirtualBox

1. Download VirtualBox 7.x from https://www.virtualbox.org/wiki/Downloads
2. Run the installer with default settings
3. After install, verify it works by opening **PowerShell** and running:

```powershell
& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" --version
```

Expected output: `7.x.x` (any 7.x version is fine)

---

## Step 2 — Install Python

1. Download Python 3.10+ from https://www.python.org/downloads/
2. During install, **check "Add Python to PATH"**
3. Verify in PowerShell:

```powershell
python --version
```

Expected output: `Python 3.10.x` or newer

---

## Step 3 — Install Required Python Libraries

Open PowerShell and run this single command:

```powershell
pip install flask flask-sock paramiko websockify
```

**What each library does:**
| Library | Purpose |
|---|---|
| `flask` | Web server that powers the browser UI |
| `flask-sock` | WebSocket support for real-time terminal |
| `paramiko` | SSH client — connects to VMs from the server |
| `websockify` | WebSocket-to-TCP bridge for the Kali VNC desktop |

To verify all libraries installed correctly:

```powershell
python -c "import flask, flask_sock, paramiko, websockify; print('All OK')"
```

Expected output: `All OK`

---

## Step 4 — Get the VM Images

The app requires specific VM image files to run scenarios. Place them in a folder on your machine.

**Required images:**

| File / Folder | Used by Scenarios | Notes |
|---|---|---|
| `emyers_unbuntu_vsftpd.ova` | All scenarios | Ubuntu 18 with vulnerable vsftpd service |
| `pfSense_export.ova` | 1, 3, 4, 5 | Pre-configured pfSense firewall |
| `emyers-vulnhu-php/` | 1, 2, 4, 5 | Debian VM with PHP-CGI vuln — folder contains a `.vbox` file |
| `kali-linux-2025.4-virtualbox-amd64/` | 3, 5 | Kali Linux with VNC — folder contains a `.vbox` file |

Obtain these images from your instructor or course materials.

---

## Step 5 — Clone and Configure the App

```powershell
git clone https://github.com/chasinrukup/virtual_simulations.git virtual_simulations_web
cd virtual_simulations_web
git checkout web
```

Open `web_config.py` in any text editor and set the path to your VM images folder:

```python
# web_config.py
IMAGES_DIR = r"C:\path\to\your\images\folder"
```

**Example** — if your images are at `C:\Users\john\Downloads\lab_images`:

```python
IMAGES_DIR = r"C:\Users\john\Downloads\lab_images"
```

---

## Step 6 — Register the VirtualBox VMs

The `emyers-vulnhu-php` and `kali-linux-2025.4-virtualbox-amd64` folders are VirtualBox VM folders (not OVA files). They need to be registered with VirtualBox before the app can clone them.

Run these commands, replacing the paths with where your images actually are:

```powershell
& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" registervm "C:\path\to\images\emyers-vulnhu-php\emyers-vulnhu-php.vbox"

& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" registervm "C:\path\to\images\kali-linux-2025.4-virtualbox-amd64\kali-linux-2025.4-virtualbox-amd64.vbox"
```

Verify they are registered:

```powershell
& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" list vms
```

You should see `emyers-vulnhu-php` and `kali-linux-2025.4-virtualbox-amd64` in the list.

---

## Step 7 — Start the App

```powershell
cd virtual_simulations_web
python app.py
```

Expected output:
```
  Virtual Network Simulation Lab
  Open in browser: http://localhost:8080
```

Open your browser and go to **http://localhost:8080**

---

## Usage

### Deploy a prebuilt scenario

1. Click a scenario card in the left sidebar
2. Review the description in the popup
3. Click **Deploy** — VMs import, networks wire up, VMs start (takes 1–5 minutes)
4. Watch the **Deployment Log** at the bottom for live progress
5. Once VMs show green **running** badges, click any VM name to SSH in

### SSH into a VM

- Click a VM name in the **Network Topology** or **VM Status** panel
- A dialog shows the pre-filled IP, username, and password
- Click **Open Terminal** — a terminal opens in the browser

### Run a ping test

- Click **Ping All VMs** after a scenario finishes deploying
- The app SSHs into each VM and pings all others — results appear in the log

### Stop / delete a lab

- **Stop All** — shuts down all VMs (preserves their disk)
- **Delete Lab** — powers off and removes all VMs from VirtualBox

---

## Default VM Credentials

| VM Image | Username | Password |
|---|---|---|
| `emyers_unbuntu_vsftpd` | `john` | `admin` |
| `emyers-vulnhu-php` | `user` | `live` |
| Kali Linux | `kali` | `kali` |
| pfSense (web UI) | `admin` | `pfsense` |

---

## Prebuilt Scenarios

| # | Name | Subnets | VMs | Purpose |
|---|---|---|---|---|
| 1 | Firewall Basics | WAN + LAN | vsftpd, PHP-CGI, pfSense | Learn how a firewall segments two subnets |
| 2 | Flat Vulnerability Lab | LAN only | vsftpd, PHP-CGI | Scanning/exploitation without a firewall |
| 3 | Segmented Attack/Defense | WAN + LAN | Kali, vsftpd, pfSense | Attacker on WAN vs. defender behind pfSense |
| 4 | Multi-Zone Network | WAN + LAN + DMZ | vsftpd, PHP-CGI, FW1, FW2 | Two firewalls, three isolated zones |
| 5 | Enterprise Network | WAN + LAN + DMZ | Kali, vsftpd, PHP-CGI, pfSense | One firewall managing three zones |

**Recommended starting point:** Scenario 2 — no firewall, just two VMs, simplest to verify.

---

## Project Structure

```
virtual_simulations_web/
├── app.py                  # Flask server — all API routes, SSH sessions, state
├── web_config.py           # IMAGES_DIR and port settings  ← edit this first
├── deployer.py             # Orchestrates VM import → NIC wiring → start
├── prebuilt.py             # Scenario definitions (subnets, VMs, firewalls)
├── vm_manager.py           # VBoxManage wrappers (create, clone, start, delete)
├── network_manager.py      # Host-only adapter management + DHCP
├── firewall_manager.py     # pfSense NIC assignment
├── adapter_manager.py      # Low-level VirtualBox adapter + DHCP helpers
├── validator.py            # Config validation before deploy
├── models.py               # LabConfig, Subnet, VMConfig, FirewallConfig dataclasses
├── logger.py               # Shared logger
├── vbox.py                 # VBoxManage subprocess wrapper
├── templates/
│   └── index.html          # Single-page UI
└── static/
    ├── app.js              # Frontend JS (polling, SSH terminal, wizard)
    └── style.css           # UI styles
```

---

## Troubleshooting

**`pip` command not found**
- Make sure Python was installed with "Add to PATH" checked
- Try `python -m pip install flask flask-sock paramiko websockify` instead

**`VBoxManage` not found**
- VirtualBox is not on your PATH. Use the full path:
  `& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" --version`

**VM fails to import — "already exists" error**
- A previous deployment left stale VMs. Delete them in the app with **Delete Lab**, or manually:
  ```powershell
  & "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" unregistervm "Target_vsftpd" --delete
  ```

**VM shows "running" but SSH gives "timed out"**
- Wait 30–60 seconds for the VM to fully boot and get a network address
- Click the **Ping All VMs** button to confirm connectivity
- If it persists, click the VM name, clear the IP field, and type the IP shown in the VM's console window

**SSH "Authentication failed" for PHP-CGI VM**
- Use `user` / `live` (not `john` / `admin`) — see credentials table above

**Cross-subnet ping fails through pfSense**
- pfSense blocks WAN→LAN by default — this demonstrates firewall segmentation
- To allow traffic: access the pfSense web UI at `https://<pfsense-lan-ip>` and add a WAN pass rule

**Kali desktop shows blank / noVNC error**
- `websockify` must be installed: `pip install websockify`
- VNC must be running inside Kali. Click the VM name in the UI — the app starts it automatically via SSH

**Server loses track of running VMs after restart**
- In-memory state is lost on restart. Running VMs continue in VirtualBox unaffected.
- Just click **Deploy** again on the same scenario — the app reconnects to the existing VMs.
