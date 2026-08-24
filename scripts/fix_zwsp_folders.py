#!/usr/bin/env python3
"""
Fix invisible Zero-Width Space (U+200B) characters in Google Drive folder names.
Run this script on the Lightsail server where rclone is configured.

Usage: python3 fix_zwsp_folders.py
"""
import subprocess
import sys


def fix_folder_names():
    base = "gdrive:Obsidian/Knowledge Base/"

    print(f"Scanning: {base}")
    result = subprocess.run(
        ["rclone", "lsf", "--dirs-only", base],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"❌ Error listing {base}: {result.stderr}")
        sys.exit(1)

    fixed = 0
    for line in result.stdout.strip().split('\n'):
        dirname = line.rstrip('/')
        if not dirname:
            continue
        if '\u200b' in dirname:
            clean_name = dirname.replace('\u200b', '')
            print(f"\n🔍 Found ZWS in: '{clean_name}' (hidden char detected)")
            print(f"   Renaming on Google Drive...")
            src = f"{base}{dirname}"
            dst = f"{base}{clean_name}"
            proc = subprocess.run(
                ["rclone", "moveto", src, dst],
                capture_output=True, text=True, timeout=60
            )
            if proc.returncode == 0:
                print(f"   ✅ Fixed!")
                fixed += 1
            else:
                print(f"   ❌ Failed: {proc.stderr}")
        else:
            print(f"✅ OK: {dirname}")

    print(f"\n{'='*40}")
    print(f"Done! Fixed {fixed} folder(s).")
    if fixed > 0:
        print("Your Telegram bot should now work correctly.")
        print("Test with /brief in Telegram!")


if __name__ == "__main__":
    fix_folder_names()
