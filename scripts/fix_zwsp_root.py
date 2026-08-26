#!/usr/bin/env python3
import subprocess
import sys

def fix_folder_names():
    base = "gdrive:"
    print(f"Scanning root: {base}")
    result = subprocess.run(
        ["rclone", "lsf", "--dirs-only", base],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"Error listing {base}: {result.stderr}")
        sys.exit(1)

    fixed = 0
    for line in result.stdout.strip().split('\n'):
        dirname = line.rstrip('/')
        if not dirname: continue
        if 'Obsidian' in dirname:
            print(f"Found Obsidian folder candidate, repr: {repr(dirname)}")
            if '\u200b' in dirname:
                clean_name = dirname.replace('\u200b', '')
                print(f"Found ZWS in root folder! Renaming to '{clean_name}'...")
                src = f"{base}{dirname}"
                dst = f"{base}{clean_name}"
                proc = subprocess.run(["rclone", "moveto", src, dst], capture_output=True, text=True, timeout=60)
                if proc.returncode == 0:
                    print("Fixed!")
                    fixed += 1
                else:
                    print(f"Failed: {proc.stderr}")
            elif dirname.endswith(' '):
                clean_name = dirname.rstrip(' ')
                print(f"Found trailing space in root folder! Renaming to '{clean_name}'...")
                src = f"{base}{dirname}"
                dst = f"{base}{clean_name}"
                proc = subprocess.run(["rclone", "moveto", src, dst], capture_output=True, text=True, timeout=60)
                if proc.returncode == 0:
                    print("Fixed!")
                    fixed += 1
                else:
                    print(f"Failed: {proc.stderr}")
            elif dirname != 'Obsidian':
                print(f"Folder name is {repr(dirname)}, does not exactly match 'Obsidian'.")
    
    print(f"Done! Fixed {fixed} root folders.")

if __name__ == "__main__":
    fix_folder_names()
