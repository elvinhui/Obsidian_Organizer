"""
Session archiver — saves completed debugging sessions to Obsidian.
"""
import os
import datetime
import logging

from config import OBSIDIAN_BASE_PATH

logger = logging.getLogger(__name__)

DEBUGGER_ARCHIVE_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "认知调试记录")

def archive_session(dialogue_markdown: str):
    """Archives the completed cognitive debugging session to Obsidian."""
    os.makedirs(DEBUGGER_ARCHIVE_DIR, exist_ok=True)
    
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H%M")
    date_str = now.strftime("%Y-%m-%d %H:%M")
    filename = f"认知调试_{timestamp}.md"
    filepath = os.path.join(DEBUGGER_ARCHIVE_DIR, filename)
    
    frontmatter = f"""---
创建时间: {date_str}
标签: #认知调试 #五连问 #苏格拉底
---
"""
    
    full_content = frontmatter + dialogue_markdown
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_content)
        logger.info(f"Cognitive debugging session archived to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to archive session: {e}")
        return None
