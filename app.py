#!/usr/bin/env python3
"""
LAN Drop - Standalone, zero-config, bi-directional local network file transfer & streaming tool.
Single-file Python application.
"""

import os
import sys
import io
import time
import socket
import re
import urllib.parse
import threading
import webbrowser
from pathlib import Path
from typing import Generator

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    import uvicorn
    from fastapi import FastAPI, Request, HTTPException, status
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    import qrcode
except ImportError:
    print("\n[!] Missing dependencies detected. Please install them:")
    print("    pip install -r requirements.txt\n")
    sys.exit(1)

# --- Configuration & Directories ---
BASE_DIR = Path(__file__).resolve().parent
TRANSFER_DIR = BASE_DIR / "transfers"
TRANSFER_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB Stream Chunk Buffer (Prevents RAM spikes)

# --- Helper Functions ---
def get_local_ip() -> str:
    """Accurately detects the primary LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def get_all_local_ips() -> list:
    """Returns all active LAN IPv4 addresses on the host (Ethernet and Wi-Fi)."""
    ips = []
    primary = get_local_ip()
    if not primary.startswith("127."):
        ips.append(primary)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips if ips else ["127.0.0.1"]

def find_free_port(start_port: int = 8000, max_attempts: int = 100) -> int:
    """Finds an available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("0.0.0.0", port)) != 0:
                return port
    # Fallback to OS assigned free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def sanitize_filename(filename: str) -> str:
    """Sanitizes filename and strips path traversal characters."""
    filename = urllib.parse.unquote(filename)
    filename = os.path.basename(filename)
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", filename).strip()
    return cleaned if cleaned else "unnamed_file"

def get_unique_filepath(directory: Path, filename: str) -> Path:
    """Appends numerical suffix if target file already exists to avoid overwriting."""
    target = directory / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1

def format_size(size_bytes: int) -> str:
    """Converts bytes to human-readable string units."""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"

# --- FastAPI Application ---
app = FastAPI(title="LAN Drop", docs_url=None, redoc_url=None)

# --- Frontend HTML / CSS / JS (Single-page Embedded) ---
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>LAN Drop | Fast & Unlimited Local File Transfer</title>
  <style>
    :root {
      --bg-primary: #0b0f19;
      --bg-secondary: #131b2e;
      --bg-card: rgba(23, 32, 54, 0.7);
      --accent: #38bdf8;
      --accent-hover: #0ea5e9;
      --accent-glow: rgba(56, 189, 248, 0.25);
      --success: #10b981;
      --danger: #ef4444;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --border-color: rgba(255, 255, 255, 0.08);
      --radius: 16px;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      background-color: var(--bg-primary);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 16px;
      overflow-x: hidden;
      background-image: 
        radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.12) 0px, transparent 50%);
    }

    .container {
      width: 100%;
      max-width: 680px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    /* Header */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: var(--bg-card);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-icon {
      width: 40px;
      height: 40px;
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      box-shadow: 0 4px 14px var(--accent-glow);
    }

    .brand-text h1 {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.5px;
    }

    .brand-text span {
      font-size: 0.75rem;
      color: var(--accent);
      font-weight: 500;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .qr-header-btn {
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.3);
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }

    .qr-header-btn:hover {
      background: rgba(56, 189, 248, 0.3);
      transform: translateY(-1px);
    }

    .status-badge {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.75rem;
      background: rgba(16, 185, 129, 0.15);
      color: var(--success);
      padding: 6px 12px;
      border-radius: 20px;
      font-weight: 600;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }

    .status-dot {
      width: 8px;
      height: 8px;
      background-color: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--success);
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(0.8); }
      100% { opacity: 1; transform: scale(1); }
    }

    /* Upload Card */
    .upload-card {
      background: var(--bg-card);
      backdrop-filter: blur(12px);
      border: 2px dashed var(--border-color);
      border-radius: var(--radius);
      padding: 32px 20px;
      text-align: center;
      cursor: pointer;
      transition: all 0.25s ease;
      position: relative;
    }

    .upload-card:hover, .upload-card.dragover {
      border-color: var(--accent);
      background: rgba(56, 189, 248, 0.05);
      transform: translateY(-2px);
    }

    .upload-icon {
      width: 64px;
      height: 64px;
      background: var(--bg-secondary);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 16px;
      font-size: 28px;
      color: var(--accent);
      border: 1px solid var(--border-color);
    }

    .upload-title {
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 6px;
    }

    .upload-subtitle {
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    .file-input {
      display: none;
    }

    /* Active Upload Queue */
    .queue-section {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .queue-item {
      background: var(--bg-card);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }

    .queue-info {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }

    .queue-header-left {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      flex: 1;
    }

    .queue-name {
      font-size: 0.9rem;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .queue-stats {
      font-size: 0.75rem;
      color: var(--accent);
      font-weight: 500;
      white-space: nowrap;
    }

    .btn-cancel-upload {
      background: rgba(239, 68, 68, 0.15);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.3);
      padding: 4px 8px;
      border-radius: 8px;
      font-size: 0.75rem;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .btn-cancel-upload:hover {
      background: rgba(239, 68, 68, 0.3);
    }

    .progress-bar-bg {
      width: 100%;
      height: 8px;
      background: var(--bg-secondary);
      border-radius: 4px;
      overflow: hidden;
    }

    .progress-bar-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), #818cf8);
      border-radius: 4px;
      transition: width 0.2s ease;
    }

    .queue-footer {
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      color: var(--text-muted);
    }

    /* Files Section */
    .files-section {
      background: var(--bg-card);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 20px 16px;
    }

    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .section-title {
      font-size: 1rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .file-count-badge {
      font-size: 0.75rem;
      background: var(--bg-secondary);
      padding: 2px 8px;
      border-radius: 12px;
      color: var(--text-muted);
    }

    .refresh-btn {
      background: var(--bg-secondary);
      color: var(--text-main);
      border: 1px solid var(--border-color);
      padding: 6px 12px;
      border-radius: 10px;
      font-size: 0.8rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s ease;
    }

    .refresh-btn:hover {
      background: var(--accent);
      color: #fff;
    }

    .file-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .file-card {
      background: rgba(19, 27, 46, 0.6);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 12px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      transition: transform 0.2s, background 0.2s;
    }

    .file-card:hover {
      background: rgba(19, 27, 46, 0.9);
      transform: translateX(2px);
    }

    .file-icon {
      font-size: 22px;
      min-width: 36px;
      height: 36px;
      background: var(--bg-secondary);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .file-details {
      flex: 1;
      min-width: 0;
    }

    .file-name {
      font-size: 0.9rem;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 2px;
      color: var(--text-main);
    }

    .file-meta {
      font-size: 0.75rem;
      color: var(--text-muted);
      display: flex;
      gap: 10px;
    }

    .file-actions {
      display: flex;
      gap: 6px;
    }

    .btn-download {
      background: linear-gradient(135deg, #0284c7, var(--accent));
      color: white;
      border: none;
      padding: 8px 14px;
      border-radius: 10px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: opacity 0.2s;
    }

    .btn-download:hover {
      opacity: 0.9;
    }

    .btn-delete {
      background: rgba(239, 68, 68, 0.15);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.3);
      padding: 8px 10px;
      border-radius: 10px;
      font-size: 0.8rem;
      cursor: pointer;
      transition: background 0.2s;
    }

    .btn-delete:hover {
      background: rgba(239, 68, 68, 0.3);
    }

    .empty-state {
      text-align: center;
      padding: 36px 16px;
      color: var(--text-muted);
      font-size: 0.9rem;
    }

    .empty-state-icon {
      font-size: 32px;
      margin-bottom: 8px;
      opacity: 0.6;
    }

    /* QR Modal */
    .modal-backdrop {
      position: fixed; inset: 0;
      background: rgba(3, 6, 15, 0.78);
      backdrop-filter: blur(8px);
      display: none; place-items: center;
      z-index: 2000;
      padding: 16px;
      animation: fadeIn 0.2s ease;
    }
    .modal-backdrop.show { display: grid; }
    .modal-box {
      background: #131b2e;
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 24px 20px;
      width: min(380px, 94vw);
      text-align: center;
      box-shadow: 0 20px 50px rgba(0,0,0,0.6);
      animation: scaleIn 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    .modal-head {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 16px;
    }
    .modal-title { font-weight: 700; font-size: 1rem; color: var(--text-main); }
    .modal-close {
      background: transparent; border: none; color: var(--text-muted);
      font-size: 1.2rem; cursor: pointer; padding: 4px;
    }
    .modal-close:hover { color: var(--text-main); }
    .qr-container {
      background: #ffffff;
      padding: 14px;
      border-radius: 12px;
      display: inline-block;
      margin-bottom: 14px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .qr-container img {
      width: 190px; height: 190px; display: block;
    }
    .qr-hint {
      font-size: 0.8rem; color: var(--text-muted); margin-bottom: 16px; line-height: 1.4;
    }
    .url-box {
      display: flex; align-items: center; justify-content: space-between;
      background: rgba(0,0,0,0.3); border: 1px solid var(--border-color);
      border-radius: 10px; padding: 8px 12px; gap: 8px;
    }
    .url-text {
      font-size: 0.8rem; font-family: monospace; color: var(--accent);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .btn-copy {
      background: var(--accent); color: #04121c; border: none;
      padding: 4px 10px; border-radius: 6px; font-size: 0.75rem;
      font-weight: 700; cursor: pointer; transition: opacity 0.2s;
    }
    .btn-copy:hover { opacity: 0.9; }

    @keyframes fadeIn { from { opacity: 0; } }
    @keyframes scaleIn { from { transform: scale(0.9); opacity: 0; } }

    /* Guide Card */
    .guide-card {
      background: var(--bg-card);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .guide-title {
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .guide-steps {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
    }

    .step-item {
      display: flex;
      align-items: center;
      gap: 10px;
      background: rgba(19, 27, 46, 0.5);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 10px;
      padding: 10px 12px;
    }

    .step-badge {
      width: 26px;
      height: 26px;
      background: linear-gradient(135deg, var(--accent), #818cf8);
      color: #04121c;
      font-weight: 800;
      font-size: 0.8rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .step-content {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }

    .step-content strong {
      font-size: 0.82rem;
      color: var(--text-main);
    }

    .step-content span {
      font-size: 0.72rem;
      color: var(--text-muted);
      line-height: 1.25;
      margin-top: 2px;
    }

    /* Toast Notification */
    #toast {
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%) translateY(100px);
      background: #1e293b;
      color: white;
      padding: 10px 20px;
      border-radius: 30px;
      font-size: 0.85rem;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
      border: 1px solid var(--border-color);
      transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
      z-index: 1000;
      pointer-events: none;
    }

    #toast.show {
      transform: translateX(-50%) translateY(0);
    }
  </style>
</head>
<body>

<div class="container">
  <!-- Header -->
  <header>
    <div class="brand">
      <div class="brand-icon">⚡</div>
      <div class="brand-text">
        <h1>LAN Drop</h1>
        <span>Unlimited Local Transfer</span>
      </div>
    </div>
    <div class="header-actions">
      <button class="qr-header-btn" onclick="openQrModal()" title="Show mobile connection QR code">
        <span>📱 QR Code</span>
      </button>
      <div class="status-badge">
        <div class="status-dot"></div>
        <span>Connected</span>
      </div>
    </div>
  </header>

  <!-- How it Works Guide -->
  <div class="guide-card">
    <div class="guide-title">
      <span>💡 Quick Guide</span>
    </div>
    <div class="guide-steps">
      <div class="step-item">
        <div class="step-badge">1</div>
        <div class="step-content">
          <strong>Same Wi-Fi</strong>
          <span>Connect both devices to the same local network</span>
        </div>
      </div>
      <div class="step-item">
        <div class="step-badge">2</div>
        <div class="step-content">
          <strong>Open on Mobile</strong>
          <span>Tap <strong>📱 QR Code</strong> above to scan with phone</span>
        </div>
      </div>
      <div class="step-item">
        <div class="step-badge">3</div>
        <div class="step-content">
          <strong>Send & Stream</strong>
          <span>Drop files to transfer with zero data quota</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Upload Area -->
  <div class="upload-card" id="dropArea" onclick="document.getElementById('fileInput').click()">
    <div class="upload-icon">📁</div>
    <div class="upload-title">Send Files</div>
    <div class="upload-subtitle">Tap or drag files here (Unlimited file size)</div>
    <input type="file" id="fileInput" class="file-input" multiple onchange="handleFileSelect(this.files)">
  </div>

  <!-- Active Upload Progress Queue -->
  <div class="queue-section" id="queueContainer"></div>

  <!-- Available Files List -->
  <div class="files-section">
    <div class="section-header">
      <div class="section-title">
        <span>Files on Host</span>
        <span class="file-count-badge" id="fileCount">0</span>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="refresh-btn" onclick="openTransfersFolder()" title="Open transfers directory on host">
          <span>📂 Open Folder</span>
        </button>
        <button class="refresh-btn" onclick="fetchFiles()">
          <span>🔄 Refresh</span>
        </button>
      </div>
    </div>
    <div class="file-list" id="fileList">
      <div class="empty-state">
        <div class="empty-state-icon">📂</div>
        No files available for download yet.
      </div>
    </div>
  </div>
</div>

<!-- QR Modal -->
<div id="qrModal" class="modal-backdrop" onclick="closeQrModal(event)">
  <div class="modal-box">
    <div class="modal-head">
      <div class="modal-title">📱 Connect Mobile Device</div>
      <button class="modal-close" onclick="closeQrModal()">✕</button>
    </div>
    <div class="qr-container">
      <img id="qrImage" src="/api/qr" alt="Connection QR Code">
    </div>
    <p class="qr-hint">Scan with your phone's camera to open LAN Drop on mobile.</p>
    <div class="url-box">
      <span id="hostUrlText" class="url-text">Loading...</span>
      <button class="btn-copy" onclick="copyHostUrl()">📋 Copy</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
  let uploadQueue = [];
  let isUploading = false;
  let activeUploads = {}; // uploadId -> { xhr, file }

  function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
  }

  function openQrModal() {
    document.getElementById('hostUrlText').textContent = window.location.origin;
    document.getElementById('qrModal').classList.add('show');
  }

  function closeQrModal(e) {
    if (!e || e.target === document.getElementById('qrModal') || e.target.classList.contains('modal-close')) {
      document.getElementById('qrModal').classList.remove('show');
    }
  }

  function copyHostUrl() {
    navigator.clipboard.writeText(window.location.origin).then(() => {
      showToast('URL copied to clipboard! 📋');
    }).catch(() => {
      showToast('Could not copy URL');
    });
  }

  // Drag & Drop Handling
  const dropArea = document.getElementById('dropArea');
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
  });

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  ['dragenter', 'dragover'].forEach(name => {
    dropArea.addEventListener(name, () => dropArea.classList.add('dragover'), false);
  });

  ['dragleave', 'drop'].forEach(name => {
    dropArea.addEventListener(name, () => dropArea.classList.remove('dragover'), false);
  });

  dropArea.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFileSelect(files);
  });

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext)) return '🖼️';
    if (['mp4', 'mkv', 'mov', 'avi', 'webm'].includes(ext)) return '🎬';
    if (['mp3', 'wav', 'flac', 'aac', 'ogg'].includes(ext)) return '🎵';
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '📦';
    if (['pdf', 'doc', 'docx', 'txt', 'epub'].includes(ext)) return '📄';
    if (['apk'].includes(ext)) return '📱';
    if (['exe', 'msi', 'iso'].includes(ext)) return '💾';
    return '📁';
  }

  function handleFileSelect(files) {
    if (!files || files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      uploadQueue.push({
        id: 'upload-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9),
        file: files[i]
      });
    }
    processQueue();
  }

  function cancelUpload(uploadId) {
    // 1. If active upload, abort XHR
    if (activeUploads[uploadId]) {
      activeUploads[uploadId].xhr.abort();
      delete activeUploads[uploadId];
      isUploading = false;
      showToast('Upload cancelled ⛔');
      const card = document.getElementById(uploadId);
      if (card) {
        card.style.opacity = '0.5';
        const speedEl = document.getElementById(`${uploadId}-speed`);
        if (speedEl) {
          speedEl.textContent = 'Cancelled ⛔';
          speedEl.style.color = 'var(--danger)';
        }
        setTimeout(() => card.remove(), 1200);
      }
      processQueue();
      return;
    }

    // 2. If queued, remove from list
    const index = uploadQueue.findIndex(item => item.id === uploadId);
    if (index !== -1) {
      uploadQueue.splice(index, 1);
      const card = document.getElementById(uploadId);
      if (card) card.remove();
      showToast('Removed from queue.');
    }
  }

  function processQueue() {
    if (isUploading || uploadQueue.length === 0) return;
    const item = uploadQueue.shift();
    uploadFileStreaming(item);
  }

  function uploadFileStreaming(item) {
    isUploading = true;
    const file = item.file;
    const queueContainer = document.getElementById('queueContainer');

    const card = document.createElement('div');
    card.className = 'queue-item';
    card.id = item.id;
    card.innerHTML = `
      <div class="queue-info">
        <div class="queue-header-left">
          <div class="queue-name" title="${file.name}">${file.name}</div>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <div class="queue-stats" id="${item.id}-speed">Starting...</div>
          <button class="btn-cancel-upload" onclick="cancelUpload('${item.id}')" title="Cancel upload">
            ✕ Cancel
          </button>
        </div>
      </div>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" id="${item.id}-fill"></div>
      </div>
      <div class="queue-footer">
        <span id="${item.id}-transferred">0 / ${formatBytes(file.size)}</span>
        <span id="${item.id}-percent">0%</span>
      </div>
    `;
    queueContainer.prepend(card);

    const xhr = new XMLHttpRequest();
    activeUploads[item.id] = { xhr: xhr, file: file };

    const startTime = Date.now();
    let lastLoaded = 0;
    let lastTime = startTime;

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        const now = Date.now();
        const timeDiff = (now - lastTime) / 1000;

        if (timeDiff >= 0.5 || e.loaded === e.total) {
          const speedBytes = (e.loaded - lastLoaded) / timeDiff;
          const speedStr = formatBytes(speedBytes) + '/s';
          lastLoaded = e.loaded;
          lastTime = now;

          const speedEl = document.getElementById(`${item.id}-speed`);
          if (speedEl) speedEl.textContent = speedStr;
        }

        const fillEl = document.getElementById(`${item.id}-fill`);
        if (fillEl) fillEl.style.width = percent + '%';
        const percentEl = document.getElementById(`${item.id}-percent`);
        if (percentEl) percentEl.textContent = percent + '%';
        const transEl = document.getElementById(`${item.id}-transferred`);
        if (transEl) transEl.textContent = `${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
      }
    };

    xhr.onload = () => {
      delete activeUploads[item.id];
      isUploading = false;
      if (xhr.status >= 200 && xhr.status < 300) {
        const speedEl = document.getElementById(`${item.id}-speed`);
        if (speedEl) {
          speedEl.textContent = 'Completed ✅';
          speedEl.style.color = 'var(--success)';
        }
        showToast(`"${file.name}" transferred successfully!`);
        setTimeout(() => {
          card.remove();
        }, 3000);
        fetchFiles();
      } else {
        const speedEl = document.getElementById(`${item.id}-speed`);
        if (speedEl) {
          speedEl.textContent = 'Upload Error ❌';
          speedEl.style.color = 'var(--danger)';
        }
        showToast('Upload error occurred!');
      }
      processQueue();
    };

    xhr.onerror = () => {
      delete activeUploads[item.id];
      isUploading = false;
      const speedEl = document.getElementById(`${item.id}-speed`);
      if (speedEl) {
        speedEl.textContent = 'Connection Lost ❌';
        speedEl.style.color = 'var(--danger)';
      }
      showToast('Connection lost!');
      processQueue();
    };

    xhr.onabort = () => {
      delete activeUploads[item.id];
      isUploading = false;
    };

    // Stream large files directly without RAM buffers
    const encodedName = encodeURIComponent(file.name);
    xhr.open('POST', `/api/upload-stream?filename=${encodedName}`, true);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.send(file);
  }

  async function fetchFiles() {
    try {
      const res = await fetch('/api/files');
      const files = await res.json();
      const listContainer = document.getElementById('fileList');
      const countBadge = document.getElementById('fileCount');

      countBadge.textContent = files.length;

      if (files.length === 0) {
        listContainer.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">📂</div>
            No files available in directory.<br><span style="font-size:0.8rem; opacity:0.7;">Drop files into host "transfers" directory or upload above.</span>
          </div>`;
        return;
      }

      listContainer.innerHTML = files.map(f => `
        <div class="file-card">
          <div class="file-icon">${getFileIcon(f.name)}</div>
          <div class="file-details">
            <div class="file-name" title="${f.name}">${f.name}</div>
            <div class="file-meta">
              <span>${f.size_formatted}</span>
              <span>•</span>
              <span>${f.modified}</span>
            </div>
          </div>
          <div class="file-actions">
            <a href="/api/download/${encodeURIComponent(f.name)}" class="btn-download" download>
              ⬇️ Download
            </a>
            <button class="btn-delete" onclick="deleteFile('${encodeURIComponent(f.name)}')" title="Delete File">
              🗑️
            </button>
          </div>
        </div>
      `).join('');
    } catch (err) {
      console.error('Failed to fetch files:', err);
    }
  }

  async function deleteFile(encodedName) {
    if (!confirm('Are you sure you want to delete this file?')) return;
    try {
      const res = await fetch(`/api/files/${encodedName}`, { method: 'DELETE' });
      if (res.ok) {
        showToast('File deleted.');
        fetchFiles();
      } else {
        showToast('Failed to delete file.');
      }
    } catch (err) {
      showToast('Network error.');
    }
  }

  async function openTransfersFolder() {
    try {
      const res = await fetch('/api/open-folder', { method: 'POST' });
      if (res.ok) {
        showToast('Transfers folder opened on host 📂');
      } else {
        showToast('Failed to open folder');
      }
    } catch (e) {
      showToast('Network error');
    }
  }

  // Initial fetch
  fetchFiles();
  // Auto refresh every 10 seconds
  setInterval(fetchFiles, 10000);
</script>
</body>
</html>
"""

# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the mobile-first file transfer web client."""
    return HTMLResponse(content=INDEX_HTML)

@app.get("/api/qr")
async def get_qr_code(request: Request):
    """Generates an image QR code representing the host connection URL."""
    host = request.headers.get("host", f"{get_local_ip()}:8000")
    url = f"http://{host}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b0f19", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.post("/api/open-folder")
async def open_transfers_folder():
    """Opens the transfers folder in the host file explorer."""
    try:
        if sys.platform == "win32":
            os.startfile(str(TRANSFER_DIR))
        elif sys.platform == "darwin":
            os.system(f'open "{TRANSFER_DIR}"')
        else:
            os.system(f'xdg-open "{TRANSFER_DIR}"')
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files")
async def list_files():
    """Lists all files stored in the transfers directory."""
    files_info = []
    for entry in sorted(TRANSFER_DIR.iterdir(), key=lambda p: p.stat().st_mtime if p.is_file() else 0, reverse=True):
        if entry.is_file() and not entry.name.endswith(".part") and entry.name != ".gitkeep":
            stat = entry.stat()
            mod_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            files_info.append({
                "name": entry.name,
                "size_bytes": stat.st_size,
                "size_formatted": format_size(stat.st_size),
                "modified": mod_time
            })
    return JSONResponse(content=files_info)

@app.post("/api/upload-stream")
async def upload_file_stream(request: Request, filename: str):
    """
    Streams large uploads in chunks directly to disk to prevent memory exhaustion.
    Uses temporary .part files to safeguard against interrupted transfers.
    """
    clean_name = sanitize_filename(filename)
    if not clean_name:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    final_path = get_unique_filepath(TRANSFER_DIR, clean_name)
    temp_path = TRANSFER_DIR / f"{final_path.name}.{os.getpid()}.part"

    try:
        with open(temp_path, "wb") as f:
            async for chunk in request.stream():
                if chunk:
                    f.write(chunk)
        
        # Atomic rename once transfer finishes
        temp_path.replace(final_path)
        print(f"[+] Transfer Success: {final_path.name} ({format_size(final_path.stat().st_size)})")
        return {"status": "success", "filename": final_path.name, "size": final_path.stat().st_size}

    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        print(f"[-] Transfer Error ({clean_name}): {e}")
        raise HTTPException(status_code=500, detail=f"Transfer interrupted: {str(e)}")

def file_iterator(filepath: Path, chunk_size: int = CHUNK_SIZE) -> Generator[bytes, None, None]:
    """Streams file content in 8MB chunks without loading entire file into memory."""
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Streams file download to client with support for unlimited sizes."""
    clean_name = sanitize_filename(filename)
    target_path = (TRANSFER_DIR / clean_name).resolve()

    # Directory Traversal Protection
    if not str(target_path).startswith(str(TRANSFER_DIR.resolve())) or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    file_size = target_path.stat().st_size
    quoted_name = urllib.parse.quote(target_path.name)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_name}",
        "Content-Length": str(file_size),
        "Accept-Ranges": "bytes"
    }

    return StreamingResponse(
        file_iterator(target_path),
        media_type="application/octet-stream",
        headers=headers
    )

@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """Safely deletes specified file from transfers directory."""
    clean_name = sanitize_filename(filename)
    target_path = (TRANSFER_DIR / clean_name).resolve()

    # Directory Traversal Protection
    if not str(target_path).startswith(str(TRANSFER_DIR.resolve())) or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        target_path.unlink()
        print(f"[*] File Deleted: {clean_name}")
        return {"status": "deleted", "filename": clean_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Terminal Banner & QR Code Output ---
def print_terminal_welcome(ip: str, port: int):
    url = f"http://{ip}:{port}"
    
    print("\n" + "="*58)
    print("           [*] LAN DROP - LOCAL FILE TRANSFER [*]")
    print("="*58)
    print(f"\n[+] Server Online!")
    print(f"[+] Local IP Address: {ip}")
    print(f"[+] Port             : {port}")
    print(f"[+] Web Interface    : \033[96m\033[4m{url}\033[0m")
    print(f"[+] Transfers Folder : {TRANSFER_DIR}\n")
    print("Scan the QR code below with your phone camera")
    print("to open the web interface instantly:\n")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Print ASCII QR code in terminal
    try:
        qr.print_ascii(invert=True)
    except Exception:
        try:
            qr.print_ascii(invert=False)
        except Exception:
            print("   [QR code could not be rendered in terminal]")

    print("\n" + "-"*58)
    print(" * Ensure both devices are connected to the SAME Wi-Fi network.")
    print(" * Press Ctrl+C to stop the server.")
    print("-"*58 + "\n")

# --- Entry Point ---
def open_browser_delayed(url: str, delay: float = 1.0):
    """Opens default web browser automatically once server starts."""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = find_free_port(8000)
    server_url = f"http://{local_ip}:{port}"

    print_terminal_welcome(local_ip, port)

    # Automatically open local browser
    open_browser_delayed(server_url, delay=1.0)

    # Start FastAPI server via Uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False
    )
