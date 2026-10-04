# ⚡ LAN Drop

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**LAN Drop** is a zero-config, standalone, ultra-fast local network file transfer & streaming tool built with Python and FastAPI. It enables seamless bi-directional file sharing of **unlimited file sizes** between your PC and mobile devices (Android / iOS) over local Wi-Fi without third-party cloud uploads or complex setups.

---

## ✨ Features

- **🚀 Zero-Configuration & Auto-Discovery:**
  - Automatically identifies host machine's active local LAN IP (`192.168.x.x`).
  - Automatically finds and binds to an available TCP port.
  - Renders an instant **ASCII QR code** in the console for 1-second mobile camera connection.
- **⚡ Unlimited Size & Memory-Efficient (Streaming/Chunking):**
  - Uses an **8 MB chunk stream pipeline** directly between disk and HTTP stream.
  - Transfer 10 GB+ files smoothly with zero RAM spikes or buffer overflows.
- **📱 Mobile-First Responsive Web Interface:**
  - Modern dark glassmorphism UI embedded directly into a single-file application.
  - Multi-file drag & drop queue with live speed (MB/s), progress percentage, and cancel controls.
  - One-click file downloading, deletion, and host transfer directory opening.
- **🛡️ Resilient & Secure:**
  - Built-in **Path Traversal protection** (`../` sanitization).
  - Temporary `.part` files with atomic renaming to safeguard against interrupted transfers.
  - Automatic collision-free numbering for duplicate filenames.

---

## 📦 Installation & Quick Start

### Prerequisites
- Python 3.9+ installed
- Both devices connected to the **same Wi-Fi / Local Area Network**

### Option 1: Quick Launcher
- **Windows:** Double-click `start.bat`.
- **macOS / Linux:** Run `chmod +x start.sh && ./start.sh`.

It will install dependencies and start the server automatically.

### Option 2: Terminal / Command Line

```bash
# 1. Clone repository
git clone https://github.com/emiukob/LAN_Drop-mobile_phone-.git
cd LAN_Drop-mobile_phone-

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start LAN Drop
python app.py
```

---

## 📱 How to Use

1. Run `python app.py` on your computer.
2. **Scan the terminal QR code** with your phone's camera (or navigate to the displayed URL in your mobile browser).
3. **Send files to PC:** Tap the "Send Files" area or drag & drop files.
4. **Download files to Phone:** Tap the **"⬇️ Download"** button next to any file stored in the `transfers/` folder.
5. All received files are safely stored in the local `transfers/` directory on your PC.

---

## 🛠️ Tech Stack

- **Backend:** Python, FastAPI, Uvicorn, Python Standard Sockets
- **Frontend:** HTML5, CSS3 Glassmorphism, Vanilla JavaScript (XHR Streaming)
- **Utilities:** QRCode (Terminal ASCII Rendering)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
