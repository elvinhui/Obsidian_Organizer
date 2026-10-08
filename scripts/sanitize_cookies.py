#!/usr/bin/env python3
"""
Cookie Sanitizer for Obsidian AI Brain.
Strips all personal account login sessions (sessionid, uid, passport) from cookies.txt,
leaving only anonymous visitor tokens (ttwid, odin_tt, etc.) required for yt-dlp media extraction.
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Sensitive cookie names that represent account login state
SENSITIVE_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "sid_ucp_v1",
    "ssid_ucp_v1",
    "uid_tt",
    "uid_tt_ss",
    "passport_assist_user",
    "passport_auth_mix_state",
    "login_time",
    "is_staff_user",
    "has_biz_token",
    "user_id"
}

def sanitize_cookies(input_file: str, output_file: str):
    if not os.path.exists(input_file):
        print(f"❌ Input file not found: {input_file}")
        sys.exit(1)
        
    sanitized_lines = []
    removed_count = 0
    retained_count = 0
    
    with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                sanitized_lines.append(line)
                continue
                
            parts = stripped.split("\t")
            if len(parts) >= 6:
                cookie_name = parts[5].strip()
                if cookie_name in SENSITIVE_COOKIE_NAMES or any(cookie_name.startswith(p) for p in ["session", "passport", "sid_"]):
                    removed_count += 1
                    continue
                else:
                    retained_count += 1
                    sanitized_lines.append(line)
            else:
                sanitized_lines.append(line)
                
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(sanitized_lines)
        
    print(f"✅ Sanitization Complete!")
    print(f"   - Removed {removed_count} sensitive login/account cookies.")
    print(f"   - Retained {retained_count} anonymous visitor/anti-scraping cookies (ttwid, etc.).")
    print(f"   - Output saved to: {output_file}")

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "cookies.txt"
    dst = sys.argv[2] if len(sys.argv) > 2 else "cookies_safe.txt"
    sanitize_cookies(src, dst)
