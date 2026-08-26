# NitroStream 🚀

**NitroStream** is a lightweight, self-hosted, high-performance home media server and cloud storage system built with **Django**, **Waitress**, **Nginx**, and **Huey**. Designed to run on local hardware (such as an Acer Nitro 5), NitroStream delivers an intuitive cloud file manager, direct desktop network mounting via WebDAV, granular account-specific file sharing, asynchronous background video/image processing, video scrubbing strips, continuous swipeable galleries, and batch uploads without relying on third-party cloud services.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2+-092E20?style=for-the-badge&logo=django&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-1.24+-009639?style=for-the-badge&logo=nginx&logoColor=white)
![GPU Acceleration](https://img.shields.io/badge/NVIDIA_NVENC-GTX_1080-76B900?style=for-the-badge&logo=nvidia&logoColor=white)
![WebDAV](https://img.shields.io/badge/WebDAV-RFC_4918-blue?style=for-the-badge)

---

## ✨ Key Features

- **🖥️ Delta-Synced WebDAV Network Drive (Desktop Mount):** Mount NitroStream directly as a native network drive (e.g. `Z:` drive on Windows File Explorer, macOS Finder, or Linux) via the built-in RFC 4918 `/webdav/` endpoint with HTTP Basic Auth. Edit Word documents, code, images, and videos in desktop applications with auto delta-syncing back to NitroStream.
- **🎬 Video Scrubbing Strips (Hover Previews):** Automatically generates low-bitrate animated WebP preview strips via FFmpeg with NVIDIA NVENC/CUDA GPU acceleration fallback. Hovering over any video card in the Drive UI plays an instant looping preview without loading the full video stream.
- **🖼️ Continuous Lightbox Gallery & Mobile Swipe:** Sequential photo and video viewing with Next/Prev buttons, keyboard arrow navigation (`←` / `→`), and responsive touch swipe gestures on mobile devices.
- **👥 Dedicated Shared Drive Section:** Left sidebar section organizes all folders and files shared with your account, grouped by sharer user with avatars, item counts, and deep subfolder navigation.
- **🔒 Granular Account-Specific & Link Sharing:** Share individual files or entire folder subtrees using 128-bit cryptographically secure UUID tokens (`/share/<uuid>/`). Supports three access modes:
  - 🔒 **Private**: Author access only.
  - 👥 **Restricted (Selected Accounts)**: Share with specific NitroStream user accounts (with live username autocomplete search & multi-select chips).
  - 🌐 **Anyone with Link**: Open access for any logged-in NitroStream user with the link.
- **🛡️ Strict Subtree Security & Protected Streaming:** Tree-walking boundary validation (`is_descendant_of`) strictly prevents directory traversal outside shared folders. Media is streamed securely via Nginx `X-Accel-Redirect`.
- **📱 Mobile Responsive & Quick Upload FAB:** Off-canvas collapsible sidebar drawer with topbar hamburger button (`☰`) and a fixed floating action upload button (`+` FAB) for mobile devices.
- **⚡ Zero-Delay Asynchronous Uploads:** Files upload directly to any destination directory with real-time drag-and-drop batch upload support.
- **🔄 Automated HEIC-to-JPG Conversion:** Converts iPhone `.heic`/`.heif` photos into web-compatible `.jpg` files using Pillow and `pillow-heif` in the background.
- **🖼️ Smart Thumbnail Generation:** Automatically generates crisp poster thumbnails from video keyframes and image previews.
- **⚡ Hot-Reload Enabled WSGI:** Uses `Waitress` wrapped with `hupper` for rapid development without restarting the app manually on code changes.
- **🛡️ Secure Local Reverse Proxy:** Nginx handles static file serving, large media streaming, and client connections while proxying API requests to Waitress.

---

## 🖥️ Desktop Network Drive Mounting Guide (WebDAV)

NitroStream exposes a native RFC 4918 WebDAV endpoint at `http://<your-server-ip>/webdav/`. You can mount it directly onto your desktop operating system:

### 🪟 Windows (File Explorer / PowerShell)

**Command Line (PowerShell / Command Prompt):**
```cmd
net use Z: http://192.168.x.x/webdav /user:your_username your_password
```

**File Explorer GUI:**
1. Open **File Explorer** &rarr; Right-click **This PC** &rarr; Select **Map network drive**.
2. Choose Drive Letter: `Z:` (or any free letter).
3. In Folder enter: `http://192.168.x.x/webdav/`
4. Check **"Connect using different credentials"** and enter your NitroStream username and password.

### 🍎 macOS (Finder)
1. Open **Finder** &rarr; Press `Cmd + K` (or menu: **Go** &rarr; **Connect to Server**).
2. Server Address: `http://192.168.x.x/webdav/`
3. Click **Connect**, choose **Registered User**, and enter your NitroStream credentials.

### 🐧 Linux (davfs2)
```bash
sudo apt install davfs2
sudo mkdir -p /mnt/nitrostream
sudo mount -t davfs http://192.168.x.x/webdav/ /mnt/nitrostream
```

---

## 🏗️ Tech Stack

- **Backend Framework:** Django 5.2 (Python 3.11)
- **WSGI Application Server:** Waitress 3.0 (with `hupper` auto-reloader)
- **Reverse Proxy / Streaming:** Nginx (Windows) with `X-Accel-Redirect`
- **Task Queue / Worker:** Huey 3.3 (SQLite-backed background queue)
- **Media Processing:** FFmpeg AMD64 (`imageio-ffmpeg`), NVIDIA NVENC GPU acceleration, Pillow, `pillow-heif`
- **Protocols:** HTTP/1.1, WebDAV (RFC 4918)

---

## 📁 Repository Structure

```text
NitroStream/
├── media_manager/              # Primary Cloud Drive & Media Management App
│   ├── models.py               # User, Folder, MediaFile schemas & sharing M2M
│   ├── views.py                # REST API for drive navigation, shares, & streaming
│   ├── webdav.py               # Native RFC 4918 WebDAV server & desktop sync controller
│   ├── tasks.py                # Huey background thumbnail & video preview generation
│   ├── urls.py                 # URL routing for Web SPA, APIs, & WebDAV endpoint
│   ├── templates/
│   │   └── media_manager/
│   │       ├── landing.html    # Marketing landing page with WebDAV mount guide
│   │       ├── drive.html      # Single Page Application (SPA) file manager
│   │       └── shared_view.html# Read-only recipient shared gallery template
│   └── static/
│       └── media_manager/
│           ├── css/drive.css   # Dark theme CSS & responsive layout
│           └── js/drive.js     # SPA navigation, upload queue, & swipe gallery JS
├── serverapp/                  # Legacy media processing & conversion tasks
│   ├── models.py               # Media item schemas
│   └── tasks.py                # Huey background tasks
├── serverproject/              # Django settings & WSGI config
├── .env                        # Local environment secrets
├── manage.py                   # Django management script
├── run.py                      # Waitress runner script with hupper
├── setup.txt                   # Setup and installation instructions
├── homeserver.txt              # Architecture, endpoint specs, & operations guide
└── README.md                   # Comprehensive project documentation
```

---

## 🏃 Starting the Server Stack

To run the complete NitroStream stack on your home network, launch 3 terminal windows:

### Terminal 1: Huey Background Worker (Video Previews & Thumbnails)
```powershell
cd D:\projects\homeserver\homeserver
.\venv\Scripts\activate
python manage.py run_huey
```

### Terminal 2: Waitress WSGI Application Server
```powershell
cd D:\projects\homeserver\homeserver
.\venv\Scripts\activate
python run.py
```

### Terminal 3: Nginx Reverse Proxy (Static Files & Protected Streaming)
```powershell
cd C:\nginx
start nginx
```

Access the web interface at `http://localhost:8000` (or `http://192.168.x.x` from other devices on Wi-Fi).