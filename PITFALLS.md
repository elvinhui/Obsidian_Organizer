# 📓 Project Pitfalls & Developer Notes

This document contains a persistent knowledge base of pitfalls, bugs, and unexpected behaviors encountered during the development of the Obsidian Organizer project, along with their root causes and verified solutions.

---

## 📁 1. Google Drive Duplicate Folders Mismatch (FUSE vs rclone)

### 🔴 Symptom
Google Drive suddenly creates duplicate folder structures, such as `03 资产库_Areas (1)` right next to the original `03 资产库_Areas`, and newly synchronized notes get routed into the `(1)` folder instead of the main one.

### 🔍 Root Cause
The path written via `rclone copyto/rcat` is slightly mismatched from the path used by the local FUSE mount due to a trailing or inner space typo in the default path definition.
*   **Example**:
    - Service A (`debugger_bot.py`) default: `/mnt/gdrive/Obsidian/Knowledge Base` (no space)
    - Service B (`telegram_bot.py`) default: `/mnt/gdrive/Obsidian /Knowledge Base` (**extra space before slash**)
*   When Service B synchronizes files using `rclone`, it uploads to `gdrive:Obsidian /Knowledge Base/03 资产库_Areas/...`. Because of the trailing space, Google Drive treats it as a new path structure, fails to map it to the FUSE-mounted `Obsidian/Knowledge Base`, and automatically creates duplicate directories (like `03 资产库_Areas (1)`) on-the-fly to prevent naming collisions.

### 🟩 Verified Solution
1.  Align all default path configurations across all services/bots. Ensure they match exactly down to casing, slashes, and spaces.
2.  Eliminate the typo space (e.g., change `"Obsidian "` to `"Obsidian"`).
3.  Deploy updates to the server and restart all services:
    ```bash
    git pull
    sudo systemctl restart telegram_bot
    sudo systemctl restart debugger_bot
    ```
4.  Go to the Google Drive web interface or desktop explorer, inspect the duplicate folder (e.g. `03 资产库_Areas (1)`), merge any files back into the original directory, and delete the duplicate folder safely.

---

## 🤖 2. Telegram Bot `sendMessage` Loopback Limitation

### 🔴 Symptom
A phone automation tool (like MacroDroid) sends a JSON POST payload to Telegram's `sendMessage` API using the bot token, successfully delivering a message with prefix `[UsageStats]` into the user's chat. However, the bot's python listener script (`handle_text`) never triggers, and Gemini doesn't reply.

### 🔍 Root Cause
By Telegram API design, **bots do not receive updates for their own outgoing messages** via standard polling (`getUpdates`).
When MacroDroid triggers `sendMessage` using the bot's token, the API treats this as an *outgoing* message from the bot to the user. Consequently, the polling event loop running on the server never receives this message in the update queue, meaning `handle_text` is completely bypassed.

### 🟩 Verified Solution
Avoid routing third-party device telemetry through the Telegram API directly. Instead, host a lightweight HTTP server on the bot's server.
1.  Embed a background HTTP web server (running on a dedicated thread) inside `telegram_bot.py`:
    ```python
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    # ... handler definition ...
    server = HTTPServer(('0.0.0.0', 8080), UsageStatsHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ```
2.  Configure MacroDroid to POST telemetry directly to the bot's server IP:
    `http://<LIGHTSAIL_IP>:8080/usagestats`
3.  Ensure the server port (`8080`) is opened in the cloud provider's firewall (e.g. AWS Lightsail Networking settings).
4.  The server handler will receive the data, process it (Gemini audit + rclone write), and use the bot token to proactively notify the user.
