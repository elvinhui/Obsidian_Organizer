import os
import sys
import logging
import traceback
import datetime
from config import INBOX_DIR
from scheduler import scan_inbox, mark_task_completed
from extractor import process_url_or_path
from ai_engine import generate_structured_json
from template_engine import render_and_save
from project_explorer import explore_and_save
from daily_digest import generate_and_save_digest
from idea_to_project import process_ideas_to_projects
from anki_generator import process_anki_generation
from skill_merger import process_skill_merging
from auto_linker import process_auto_linking
from spaced_review import process_spaced_review

# Configure logging: full detail to file, only important messages to console
log_dir = r"C:\Users\KATANA 17 B13V\Documents\projects\Obsidianorganizer\AI brain log"
os.makedirs(log_dir, exist_ok=True)
current_date = datetime.date.today().strftime("%Y-%m-%d")
log_file_path = os.path.join(log_dir, f"{current_date}.log")

file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])

# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def process_task(task: dict):
    file_path = task['file_path']
    payload = task['payload']
    
    logger.info(f"Processing task from {os.path.basename(file_path)}: {payload}")
    
    # 1. Extraction
    try:
        raw_text = process_url_or_path(payload)
        logger.info(f"Successfully extracted {len(raw_text)} characters of text.")
    except Exception as e:
        logger.error(f"Failed to extract content for {payload}: {e}")
        logger.debug(traceback.format_exc())
        return False
        
    # 2. AI Structuring
    try:
        context_tag = os.path.basename(file_path)
        structured_data = generate_structured_json(raw_text, context_tag=context_tag)
        logger.info(f"Successfully structured JSON: {structured_data.get('title')}")
    except Exception as e:
        logger.error(f"Failed to structure content using AI: {e}")
        logger.debug(traceback.format_exc())
        return False
        
    # 3. Templating & Saving
    try:
        saved_path = render_and_save(structured_data)
        logger.info(f"Successfully saved to {saved_path}")
    except Exception as e:
        logger.error(f"Failed to render and save template: {e}")
        logger.debug(traceback.format_exc())
        return False
        
    # 4. Update Original Task State
    success = mark_task_completed(file_path, task['original_line'])
    return success

def main():
    logger.info("Starting Obsidian AI Brain Engine...")
    
    # Phase 1: Process pending inbox tasks
    tasks = scan_inbox(INBOX_DIR)
    if not tasks:
        logger.info("No pending tasks found in Inbox.")
    else:
        logger.info(f"Found {len(tasks)} pending tasks.")
        success_count = 0
        for task in tasks:
            if process_task(task):
                success_count += 1
        logger.info(f"Finished processing Inbox. Successfully handled {success_count}/{len(tasks)} tasks.")

    # Phase 2: Convert ideas to projects
    try:
        process_ideas_to_projects()
    except Exception as e:
        logger.error(f"Idea conversion failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 3: Anki card generation
    try:
        process_anki_generation()
    except Exception as e:
        logger.error(f"Anki generation failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 4: Generate daily digest (always runs after processing)
    try:
        logger.info("📰 Generating daily knowledge digest...")
        digest_path = generate_and_save_digest(days=1)
        if digest_path:
            logger.info(f"📰 Daily digest saved: {digest_path}")
    except Exception as e:
        logger.error(f"Daily digest generation failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 5: Explore project ideas automatically (runs once per day)
    try:
        logger.info("🔍 Starting project exploration...")
        result = explore_and_save()
        if result:
            logger.info(f"🚀 Project exploration complete: {result}")
    except Exception as e:
        logger.error(f"Project exploration failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 6: Merge similar skills in the library
    try:
        logger.info("🔄 Starting skill library deduplication...")
        process_skill_merging()
    except Exception as e:
        logger.error(f"Skill merging failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 7: Auto-link knowledge cards with [[双链]]
    try:
        logger.info("🌐 Starting knowledge graph auto-linking...")
        process_auto_linking()
    except Exception as e:
        logger.error(f"Auto-linking failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 8: Spaced repetition review scheduler
    try:
        logger.info("🧠 Starting Spaced Repetition Scheduler...")
        process_spaced_review()
    except Exception as e:
        logger.error(f"Spaced review failed: {e}")
        logger.debug(traceback.format_exc())

if __name__ == "__main__":
    main()
