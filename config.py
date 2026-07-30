import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
JINA_API_KEY = os.getenv("JINA_API_KEY")

# Paths
OBSIDIAN_BASE_PATH = r"G:\我的云端硬盘\Obsidian\Knowledge Base"
INBOX_DIR = os.path.join(OBSIDIAN_BASE_PATH, "00 Inbox (收件箱)")
SKILLS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "05 技能库")
PROJECTS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "02 项目库_Projects")
IDEAS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "01 灵感库_Ideas")
ANKI_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "Anki卡包")

# Fallback: if directories do not exist, we can create them (optional)
# os.makedirs(INBOX_DIR, exist_ok=True)
# os.makedirs(SKILLS_DIR, exist_ok=True)
