import os
import sys
import logging
import traceback
import datetime
from config import INBOX_DIR
from scheduler import scan_inbox, mark_task_completed
from extractor import process_url_or_path
from ai_engine import generate_structured_json, generate_deep_structured_json
from template_engine import render_and_save
from project_explorer import explore_and_save
from daily_digest import generate_and_save_digest
from idea_to_project import process_ideas_to_projects
from anki_generator import process_anki_generation
from skill_merger import process_skill_merging
from auto_linker import process_auto_linking
from spaced_review import process_spaced_review
from open_questions_processor import process_answered_questions, generate_weekly_cognitive_report
from conflict_cleaner import process_conflict_resolution
import uvicorn
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from laap_agent.api import app as laap_app
from laap_agent.engine import run_daily_simulation
from rss_filter import process_daily_rss_feeds
from asset_radar import process_asset_radar
from cognitive_debugger.telegram_bot import run_telegram_bot

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
        if len(raw_text) >= 20000:
            logger.info(f"Text is MASSIVE ({len(raw_text)} chars). Using Map-Reduce MOC structuring...")
            structured_data = generate_moc_structured_json(raw_text, context_tag=context_tag)
        elif len(raw_text) >= 8000:
            logger.info(f"Text is long ({len(raw_text)} chars). Using deep structuring...")
            structured_data = generate_deep_structured_json(raw_text, context_tag=context_tag)
        else:
            logger.info(f"Text is short ({len(raw_text)} chars). Using fast structuring...")
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

def run_pipeline():
    logger.info("Starting Obsidian AI Brain Engine Pipeline...")
    
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
    # Phase 9: Process answered open questions into Insights
    try:
        logger.info("💡 Scanning for answered Open Questions...")
        process_answered_questions()
    except Exception as e:
        logger.error(f"Open questions processing failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 10: Weekly Cognitive Report (Runs on Mondays)
    try:
        # weekday() == 0 is Monday
        if datetime.date.today().weekday() == 0:
            logger.info("📅 Today is Monday! Generating Weekly Cognitive Report...")
            generate_weekly_cognitive_report()
    except Exception as e:
        logger.error(f"Weekly report generation failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 12: Digital Lifeform (LAAP) Simulation
    try:
        logger.info("🧬 Running Personal LAAP Agent Forward Simulation...")
        run_daily_simulation()
    except Exception as e:
        logger.error(f"LAAP Agent simulation failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 13: 每日反脆弱认知简报 (Daily Anti-Fragile RSS Filter)
    try:
        process_daily_rss_feeds()
    except Exception as e:
        logger.error(f"Daily RSS Anti-Fragility Filter failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 14: 资产雷达监控 (Asset Radar)
    try:
        process_asset_radar()
    except Exception as e:
        logger.error(f"Asset Radar failed: {e}")
        logger.debug(traceback.format_exc())

    logger.info("Obsidian AI Brain Engine Pipeline Finished.")

def start_pipeline_in_background():
    """Run the pipeline immediately in a separate thread so it doesn't block the server startup."""
    threading.Thread(target=run_pipeline, daemon=True).start()

def main():
    logger.info("Starting Obsidian AI Brain Engine with LAAP Sidecar...")
    
    # 1. Setup Scheduler
    scheduler = BackgroundScheduler()
    # Run pipeline every 2 hours
    scheduler.add_job(run_pipeline, 'interval', hours=2)
    scheduler.start()
    
    # 2. Run pipeline once on startup
    start_pipeline_in_background()
    
    # 3. Start Cognitive Debugger Telegram Bot in background
    logger.info("🤖 Starting Cognitive Debugger Telegram Bot...")
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    
    # 4. Start FastAPI Server
    logger.info("🚀 Starting LAAP Agent FastAPI Server on port 8000...")
    uvicorn.run(laap_app, host="0.0.0.0", port=8000, log_level="info")

if __name__ == "__main__":
    main()
