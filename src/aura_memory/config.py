import os
import re
from dotenv import load_dotenv

load_dotenv()

# Raw path resolution with defensive normalization (following PITFALLS.md guidelines)
raw_base_path = os.getenv("OBSIDIAN_BASE_PATH", r"G:\我的云端硬盘\Obsidian\Knowledge Base").strip()
path_parts = [p.strip() for p in re.split(r'[/\\]', raw_base_path) if p.strip()]
if os.name == 'nt' and len(path_parts) > 0 and ':' in path_parts[0]:
    # Windows drive root like G:
    drive = path_parts[0]
    OBSIDIAN_BASE_PATH = drive + "\\" + "\\".join(path_parts[1:])
else:
    OBSIDIAN_BASE_PATH = ("/" if raw_base_path.startswith("/") else "") + "/".join(path_parts)

# Monitored knowledge directories
INBOX_DIR = os.path.join(OBSIDIAN_BASE_PATH, "00 Inbox (收件箱)")
SKILLS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "05 技能库")
PROJECTS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "02 项目库_Projects")
INSIGHTS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "07 洞见库_Insights")
AREAS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas")
REVIEW_DIR = os.path.join(AREAS_DIR, "每日复习")

WATCH_DIRS = [SKILLS_DIR, PROJECTS_DIR, INSIGHTS_DIR, REVIEW_DIR]

# AuraMemory DB Path
AURA_DB_DIR = os.path.dirname(os.path.abspath(__file__))
AURA_DB_PATH = os.getenv("AURA_DB_PATH", os.path.join(AURA_DB_DIR, "aura_memory.db"))

# Watchdog debounce settings (seconds)
WATCHER_DEBOUNCE_SECONDS = float(os.getenv("AURA_WATCHER_DEBOUNCE", "0.5"))
INBOX_DEBOUNCE_SECONDS = float(os.getenv("AURA_INBOX_DEBOUNCE", "5.0"))

# Ignore patterns (regex or substrings)
IGNORE_SUBSTRINGS = [
    ".obsidian",
    ".trash",
    ".git",
    ".pytest_cache",
    "__pycache__",
    "conflict",
    ".goutputstream",
    ".tmp"
]

IGNORE_EXTENSIONS = [
    ".tmp",
    ".crdownload",
    ".part",
    ".swp"
]
