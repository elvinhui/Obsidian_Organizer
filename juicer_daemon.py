import os
import glob
import logging
from dotenv import load_dotenv
import sys

# Ensure root dir is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.feynman_juicer.main import run_feynman_juicer

logger = logging.getLogger(__name__)

def get_possible_inbox_dirs():
    """动态获取可能的 Inbox 路径，兼容 Windows 和 Lightsail"""
    load_dotenv()
    env_inbox = os.getenv("JUICER_INBOX_DIR")
    if env_inbox and os.path.exists(env_inbox):
        return [env_inbox]
        
    return [
        r"G:\我的云端硬盘\Obsidian\Knowledge Base\00 Inbox (收件箱)",
        r"C:\Users\KATANA 17 B13V\Documents\Obsidian\Knowledge Base\00 Inbox (收件箱)",
        "/mnt/gdrive/Obsidian/Knowledge Base/00 Inbox (收件箱)"
    ]

def get_possible_output_dirs():
    """动态获取可能的技能库输出路径"""
    load_dotenv()
    env_out = os.getenv("JUICER_OUTPUT_DIR")
    if env_out and os.path.exists(env_out):
        return env_out
        
    for path in [
        r"G:\我的云端硬盘\Obsidian\Knowledge Base\02 技能库_Skills",
        r"C:\Users\KATANA 17 B13V\Documents\Obsidian\Knowledge Base\02 技能库_Skills",
        "/mnt/gdrive/Obsidian/Knowledge Base/02 技能库_Skills"
    ]:
        if os.path.exists(path):
            return path
    
    # Fallback to local
    return "juicer_output_cards"

def run_daemon():
    logger.info("Starting Feynman-Juicer Daemon...")
    inbox_dirs = get_possible_inbox_dirs()
    valid_inbox = None
    for d in inbox_dirs:
        if os.path.exists(d):
            valid_inbox = d
            break
            
    if not valid_inbox:
        logger.error("Could not find any valid Inbox directory. Please set JUICER_INBOX_DIR in .env")
        return
        
    output_dir = get_possible_output_dirs()
    os.makedirs(output_dir, exist_ok=True)
    
    # Scan all markdown files in the inbox
    md_files = glob.glob(os.path.join(valid_inbox, "**", "*.md"), recursive=True)
    logger.info(f"Scanning {len(md_files)} markdown files in {valid_inbox}")
    
    for md_file in md_files:
        run_feynman_juicer(md_file, output_dir)
        
    logger.info("Daemon sweep complete!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    run_daemon()
