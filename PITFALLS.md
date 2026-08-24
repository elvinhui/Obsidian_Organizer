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
1.  **Defensive Path Normalization**: In python, split `OBSIDIAN_BASE_PATH` by separators (`/` or `\`) and strip trailing/leading spaces from all directory name components automatically before joining them back. This completely neutralizes dirty `.env` or system environment configurations.
    ```python
    raw_base_path = os.getenv("OBSIDIAN_BASE_PATH", "/mnt/gdrive/Obsidian/Knowledge Base").strip()
    path_parts = [p.strip() for p in re.split(r'[/\\]', raw_base_path) if p.strip()]
    OBSIDIAN_BASE_PATH = ("/" if raw_base_path.startswith("/") else "") + "/".join(path_parts)
    ```
2.  Deploy updates to the server and restart all services:
    ```bash
    git pull
    sudo systemctl restart telegram_bot
    sudo systemctl restart debugger_bot
    ```
3.  Go to the Google Drive web interface or desktop explorer, inspect the duplicate folder (e.g. `03 资产库_Areas (1)`), merge any files back into the original directory, and delete the duplicate folder safely. Empty the cloud Trash afterward to prevent rclone name-resolution confusion.

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
3:  Ensure the server port (`8080`) is opened in the cloud provider's firewall (e.g. AWS Lightsail Networking settings).
4:  The server handler will receive the data, process it (Gemini audit + rclone write), and use the bot token to proactively notify the user.

---

## 🍪 3. Windows Chromium Browser Cookies Lock & Keyring Decryption Failure

### 🔴 Symptom
When downloading Douyin (TikTok) videos, the backend extractor crashes with `ERROR: unsupported keyring: "firefox"` or `PermissionError: [Errno 13] Permission denied: '.../Cookies'`.

### 🔍 Root Cause
1.  **Exclusive DB Lock**: Chrome/Edge browser maintains an exclusive OS write lock on the `Cookies` SQLite database while the browser is running.
2.  **App-Bound Encryption**: Chrome/Edge 127+ utilizes DPAPI process-bound encryption for cookies, meaning keys are locked to the browser application process itself and third-party tools cannot decrypt them directly.
3.  **Keyring Initialization Loop**: If multiple browsers are configured in a tuple (e.g., `('chrome', 'edge', 'firefox')`), a decryption/access crash in one (e.g., Firefox keyring missing or failing) triggers a fatal exception, preventing the remaining browsers from being tried. If a bare string is passed, it unpacks character-by-character, raising positional argument mismatches.

### 🟩 Verified Solution
1.  **Prioritize Local cookies.txt**: Set up a local `cookies.txt` file exported via browser extensions. It is not locked by the browser and works instantly on both Windows and Linux.
2.  **Collection unpack safety & Loop-based fallback**: In python, wrap each strategy in a try-except block and use proper list collections:
    ```python
    cookie_strategies = []
    # Try cookies.txt first
    local_cookies = os.path.join(os.path.dirname(__file__), 'cookies.txt')
    if os.path.exists(local_cookies):
        cookie_strategies.append({'cookiefile': local_cookies})
    # Fallback to browser extraction on Windows
    if os.name == 'nt':
        cookie_strategies.extend([
            {'cookiesfrombrowser': 'chrome'},
            {'cookiesfrombrowser': 'edge'}
        ])
    cookie_strategies.append({})  # No-cookies fallback
    ```

---

## 🎬 4. YouTube "Subtitles Disabled" → 403 Forbidden Audio Download Chain

### 🔴 Symptom
YouTube videos with subtitles disabled cause `youtube-transcript-api` to throw `Could not retrieve a transcript`. Audio download fallback via `yt-dlp` then fails with `HTTP Error 403: Forbidden`.

### 🔍 Root Cause
1.  **Subtitles disabled**: The video creator has not enabled captions, so `youtube-transcript-api` has nothing to fetch.
2.  **yt-dlp version lag**: Older versions of `yt-dlp` (e.g. `2026.7.4`) use stale YouTube player extraction logic. YouTube frequently rotates its anti-bot signatures, causing `403 Forbidden` on audio/video streams.
3.  **`cookiesfrombrowser` format**: The yt-dlp Python API expects a **list** (e.g. `['chrome']`), not a bare string (`'chrome'`). A bare string gets unpacked character-by-character, causing `_parse_browser_specification() takes from 1 to 4 positional arguments but 6 were given`.

### 🟩 Verified Solution
1.  **Auto-fallback in `extract_youtube()`**: Wrap the subtitle fetch in try/except; on failure, call `extract_short_video()` to download audio via yt-dlp + Groq Whisper transcription.
2.  **Keep yt-dlp up to date**: Run `pip install --upgrade yt-dlp` regularly. The jump from `2026.7.4` → `2026.8.19` immediately resolved the YouTube 403.
3.  **Always use list format**: `{'cookiesfrombrowser': ['chrome']}` not `{'cookiesfrombrowser': 'chrome'}`.

## 5. LAAP Agent Missing Feedback File
* **🔴 Symptom**: The user noticed that the "分身推演报告" (Avatar Deduction Report) was not updating or missing for the current day.
* **🔍 Root Cause**: In `src/laap_agent/engine.py`, the `run_daily_simulation()` function successfully calculated the simulation result but forgot to call `save_feedback_card(sim_result)` and `save_memory(entry)` at the end of the pipeline. The generated result was simply discarded instead of being saved to the local database and Obsidian folder.
* **🟩 Verified Solution**: Added `save_memory(entry)` and `save_feedback_card(sim_result)` calls directly before the logging statements in `run_daily_simulation()`.


## 6. SDD Agent False Positive and Model 404
* **🔴 Symptom**: `sdd_agent.py` threw an error trying to process `💣虚胖笔记扫雷报告_20260820.md` and then failed with `404 NOT_FOUND` for model `gemini-3.5-pro`.
* **🔍 Root Cause**: (1) The text `#SDD_Pending` was written as an instruction inside the Markdown report, which the scanner naively picked up as a trigger, creating a false positive. (2) The model string `gemini-3.5-pro` is not available in the active Gemini API version, leading to a 404.
* **🟩 Verified Solution**: Added a filename exclusion for `虚胖笔记扫雷报告` in `sdd_agent.py`s scanner, and downgraded the model string to a known stable `gemini-3.5-flash`.


## 7. Rclone CLI Directory Not Found (Sync Delay/Missing Folder)
* **🔴 Symptom**: Both local FUSE mount and `rclone lsf` fallback throw `directory not found` when looking for the RSS folder.
* **🔍 Root Cause**: The user created the folder locally via Google Drive Desktop on Windows, but the sync engine paused or failed to upload the `RSS Feed` directory to the Google Drive cloud. Thus, the Linux server (querying the cloud) literally cannot see it.
* **🟩 Verified Solution**: Advised user to log into Google Drive Web to verify the existence of the folder, and force-sync Google Drive Desktop on their local machine.

