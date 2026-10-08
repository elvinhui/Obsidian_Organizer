# 🤖 Obsidian Organizer - AI Coding Guidelines & Pitfall Logging

Always follow these rules when working in this repository:

## 📓 Mandatory Pitfall Tracking & Auto-Logging
Whenever you fix a bug, encounter a configuration error (e.g. Google Drive duplicate folder paths, trailing spaces, directory case issues), resolve a tool constraint (e.g. Telegram Bot self-sendMessage polling loop limit), or solve a deployment pipeline crash:
1.  **Read `PITFALLS.md`** at the project root to check if it has been documented.
2.  **Add a new entry to `PITFALLS.md`** detailing:
    *   **🔴 Symptom**: The error message, log line, or visual failure.
    *   **🔍 Root Cause**: Why it happened (the underlying system/casing/logic cause).
    *   **🟩 Verified Solution**: The exact steps/code changes needed to resolve it.
3.  Do NOT ask the user for permission to log these entries; always update `PITFALLS.md` automatically as part of your bug-fixing phase.

## 📁 Paths Casing and Trailing Spaces Safety
*   Never write paths with inner or trailing spaces (e.g. `/mnt/gdrive/Obsidian /` or `03 资产库_Areas `).
*   Double-check that paths match the default FUSE mount `OBSIDIAN_BASE_PATH = "/mnt/gdrive/Obsidian/Knowledge Base"`.
*   Any rclone operation MUST map precisely to this path format to prevent Google Drive from creating duplicate folders (e.g. `03 资产库_Areas (1)`).
