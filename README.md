# NitroStream 🚀

**NitroStream** is a lightweight, self-hosted, high-performance home media server built with **Django**, **Waitress**, **Nginx**, and **Huey**. Designed to run on local hardware (such as an Acer Nitro 5), NitroStream delivers asynchronous background video/image processing, streaming-ready media playback, real-time file searching, and batch uploads without relying on third-party cloud services.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.2+-092E20?style=for-the-badge&logo=django&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-1.24+-009639?style=for-the-badge&logo=nginx&logoColor=white)
![GPU Acceleration](https://img.shields.io/badge/NVIDIA_NVENC-GTX_1080-76B900?style=for-the-badge&logo=nvidia&logoColor=white)

---

## ✨ Key Features

- **⚡ Zero-Delay Asynchronous Uploads:** Files upload directly to the filesystem and instantly confirm without blocking the user interface.
- **🔄 Automated HEIC-to-JPG Conversion:** Converts iPhone `.heic`/`.heif` photos into web-compatible `.jpg` files using Pillow and `pillow-heif` in the background.
- **🎥 Hardware-Accelerated Video Encoding:** Automatically converts heavy `.mkv` files into web-optimized `.mp4` using **NVIDIA NVENC (GTX 1080)** GPU acceleration with a CPU fallback (`libx264`).
- **🖼️ Smart Thumbnail Generation:** Automatically generates low-res image previews and video keyframe thumbnails.
- **🔍 Real-Time Gallery Search:** Instantly filter media items by filename or category.
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
├── serverapp/                  # Core Django application app
│   ├── models.py               # Media item schemas
│   ├── tasks.py                # Huey background tasks (FFmpeg/HEIC processing)
│   ├── views.py                # AJAX upload logic & category sorting
│   └── templates/
│       └── image_list.html     # Responsive media gallery frontend
├── serverproject/              # Django settings & WSGI config
├── .env                        # Local environment secrets (ignored by Git)
├── manage.py                   # Django management script
├── run.py                      # Waitress runner script with hupper
├── sonar-project.properties    # SonarQube scanner properties
└── README.md                   # Project documentation