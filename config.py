import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
JINA_API_KEY = os.getenv("JINA_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Paths
OBSIDIAN_BASE_PATH = r"G:\我的云端硬盘\Obsidian\Knowledge Base"
INBOX_DIR = os.path.join(OBSIDIAN_BASE_PATH, "00 Inbox (收件箱)")
SKILLS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "05 技能库")
PROJECTS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "02 项目库_Projects")
IDEAS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "01 灵感库_Ideas")
ANKI_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "Anki卡包")
INSIGHTS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "07 洞见库_Insights")
ARCHIVES_DIR = os.path.join(OBSIDIAN_BASE_PATH, "06 归档库_Archives")
OPEN_QUESTIONS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "开放性思考")
WEEKLY_ROLLUP_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每周复盘")
LAAP_FEEDBACK_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "数字生命体反馈")
LAAP_IDENTITY_FILE = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "数字生命体人设.md")
DAILY_BRIEFING_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每日简报")
RSS_FEEDS_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "RSS Feed")
ASSET_RADAR_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "资产雷达")
POLAR_STAR_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "北极星看板")
SKILL_COMPOUNDING_DIR = os.path.join(POLAR_STAR_DIR, "技能复利记录")

# Fallback: if directories do not exist, we can create them (optional)
# os.makedirs(INBOX_DIR, exist_ok=True)
# os.makedirs(SKILLS_DIR, exist_ok=True)
