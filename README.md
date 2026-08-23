# NitroStream 🚀

**NitroStream** is a lightweight, self-hosted, high-performance home media server and cloud storage system built with **Django**, **Waitress**, **Nginx**, and **Huey**. Designed to run on local hardware (such as an Acer Nitro 5), NitroStream delivers a file manager, granular account-specific file sharing, asynchronous background video/image processing, streaming-ready media playback, real-time file searching, and batch uploads without relying on third-party cloud services.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.2+-092E20?style=for-the-badge&logo=django&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-1.24+-009639?style=for-the-badge&logo=nginx&logoColor=white)
![GPU Acceleration](https://img.shields.io/badge/NVIDIA_NVENC-GTX_1080-76B900?style=for-the-badge&logo=nvidia&logoColor=white)

---

## ✨ Key Features

- **📁 File Manager:** Full Single Page Application (SPA) with nested folder management, interactive sidebar tree, breadcrumb navigation, grid/list view toggles, and real-time gallery search.
- **📱 Mobile Responsive & Quick Upload FAB:** Off-canvas collapsible sidebar drawer with topbar hamburger button (`☰`) and a fixed floating action upload button (`+` FAB) for mobile devices.
- **🔒 Granular Account-Specific & Link Sharing:** Share individual files or entire folder subtrees using 128-bit cryptographically secure UUID tokens (`/share/<uuid>/`). Supports three access modes:
  - 🔒 **Private**: Author access only.
  - 👥 **Restricted (Selected Accounts)**: Share with specific NitroStream user accounts (with live username autocomplete search & multi-select chips).
  - 🌐 **Anyone with Link**: Open access for any logged-in NitroStream user with the link.
- **🛡️ Strict Subtree Security & Protected Streaming:** Tree-walking boundary validation (`is_descendant_of`) strictly prevents directory traversal outside shared folders. Media is streamed securely via Nginx `X-Accel-Redirect`.
- **⚡ Zero-Delay Asynchronous Uploads:** Files upload directly to any destination directory with real-time drag-and-drop batch upload support.
- **🔄 Automated HEIC-to-JPG Conversion:** Converts iPhone `.heic`/`.heif` photos into web-compatible `.jpg` files using Pillow and `pillow-heif` in the background.
- **🎬 Video Scrubbing Strips (Hover Previews):** Automatically generates low-bitrate animated WebP preview strips via FFmpeg (with NVIDIA NVENC/CUDA hardware acceleration fallback). Hovering over any video card in the Drive UI plays an instant looping preview without loading the full video stream.
- **🖼️ Smart Thumbnail Generation:** Automatically generates crisp poster thumbnails from video keyframes and image previews.
- **⚡ Hot-Reload Enabled WSGI:** Uses `Waitress` wrapped with `hupper` for rapid development without restarting the app manually on code changes.
- **🛡️ Secure Local Reverse Proxy:** Nginx handles static file serving, large media streaming, and client connections while proxying API requests to Waitress.

---

## 🏗️ Tech Stack

- **Backend Framework:** Django (Python 3.11)
- **WSGI Application Server:** Waitress (with `hupper` for dev reloading)
- **Reverse Proxy / Static Server:** Nginx (Windows)
- **Task Queue / Worker:** Huey (SQLite-backed lightweight queue)
- **Media Processing:** FFmpeg (NVENC GPU accelerated), Pillow, `pillow-heif`

---

## 📁 Repository Structure

```text
NitroStream/
├── .github/
│   └── workflows/
│       └── sonarqube.yml       # GitHub Actions CI pipeline for SonarQube
├── media_manager/              # Cloud Drive & Granular Share Manager app
│   ├── models.py               # User, Folder, MediaFile schemas & share relationships
│   ├── views.py                # Rest API for drive navigation, user search, & secure sharing
│   ├── urls.py                 # Route definitions for drive, shares, & streaming
│   ├── templates/
│   │   └── media_manager/
│   │       ├── drive.html      # file manager style SPA shell template
│   │       └── shared_view.html# Read-only recipient shared SPA template
│   └── static/
│       └── media_manager/
│           ├── css/drive.css   # Dark theme CSS & responsive layout
│           └── js/drive.js     # SPA navigation, upload, & share modal JS
├── serverapp/                  # Legacy media processing & conversion tasks
│   ├── models.py               # Media item schemas
│   └── tasks.py                # Huey background tasks (FFmpeg/HEIC processing)
├── serverproject/              # Django settings & WSGI config
├── .env                        # Local environment secrets (ignored by Git)
├── manage.py                   # Django management script
├── run.py                      # Waitress runner script with hupper
├── setup.txt                   # Setup and installation instructions
├── homeserver.txt              # Home server architecture and operations guide
└── README.md                   # Project documentation
```