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
from polar_star_dashboard import generate_dashboard
from aura_memory.api import router as aura_memory_router
from aura_memory.engine import get_engine

# Unify AuraMemory into FastAPI server
laap_app.include_router(aura_memory_router)

# Configure logging: full detail to file, only important messages to console
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_dir = os.getenv("LOG_DIR", os.path.join(project_root, "AI brain log"))
os.makedirs(log_dir, exist_ok=True)
current_date = datetime.date.today().strftime("%Y-%m-%d")
log_file_path = os.path.join(log_dir, f"{current_date}.log")

file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Force root logger configuration to bypass module basicConfig blocks
root_logger = logging.getLogger()
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)
root_logger.setLevel(logging.INFO)

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
    
    # ------------------ FEYNMAN JUICER INTEGRATION ------------------
    import re
    url_match = re.search(r'(https?://[^\s]+)', payload)
    target = url_match.group(1) if url_match else payload
    video_domains = ["youtube.com", "youtu.be", "douyin.com", "v.douyin.com", "bilibili.com", "b23.tv"]
    
    if any(d in target for d in video_domains):
        logger.info("🎬 Video detected! Routing to Feynman-Juicer Multi-modal Pipeline...")
        from feynman_juicer.media_extractor import MediaExtractor
        from feynman_juicer.juicer_engine import JuicerEngine
        from config import SKILLS_DIR
        
        try:
            extractor = MediaExtractor()
            engine = JuicerEngine()
            
            # 1. Physical Extraction
            audio_path = extractor.download_audio(target)
            
            # 2. Multi-modal Juicing
            data = engine.juice_audio(audio_path)
            
            # 3. Rendering
            md_content = engine.render_obsidian_card(data, target)
            safe_title = "".join(c for c in data.get('title', 'Untitled') if c.isalnum() or c in (' ', '-', '_')).strip()
            
            out_file = os.path.join(SKILLS_DIR, f"{safe_title}.md")
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(md_content)
                
            logger.info(f"✅ Feynman-Juicer generated: {out_file}")
            
            # Cleanup
            if os.path.exists(audio_path):
                os.remove(audio_path)
                
            # 4. Update Original Task State
            return mark_task_completed(file_path, task['original_line'])
            
        except Exception as e:
            logger.error(f"Feynman Juicer failed for {target}: {e}")
            return False
    # ----------------------------------------------------------------
    
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
    aura_engine = get_engine()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    today_compact = datetime.date.today().strftime("%Y%m%d")
    from config import OBSIDIAN_BASE_PATH, LAAP_FEEDBACK_DIR, POLAR_STAR_DIR
    
    # Phase 0: Resolve Google Drive conflicts (Lightweight, every cycle)
    try:
        process_conflict_resolution()
    except Exception as e:
        logger.error(f"Conflict resolution failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 1: Process pending inbox tasks (Fallback for unhandled items)
    tasks = scan_inbox(INBOX_DIR)
    if not tasks:
        logger.debug("No pending tasks found in Inbox.")
    else:
        logger.info(f"Found {len(tasks)} pending tasks in Inbox.")
        success_count = 0
        for task in tasks:
            if process_task(task):
                success_count += 1
        logger.info(f"Finished processing Inbox: {success_count}/{len(tasks)} handled.")

    # Phase 2: Convert ideas to projects (Only if pending ideas exist)
    try:
        process_ideas_to_projects()
    except Exception as e:
        logger.error(f"Idea conversion failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 3: Anki card generation (Only if pending cards exist)
    try:
        process_anki_generation()
    except Exception as e:
        logger.error(f"Anki generation failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 4: Generate daily digest (Daily idempotent: Once per day)
    digest_path = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每日复盘", f"知识日报_{today_str}.md")
    if not os.path.exists(digest_path) and aura_engine.should_run_task("daily_digest", interval_days=1):
        try:
            logger.info("📰 Generating daily knowledge digest (first run today)...")
            res = generate_and_save_digest(days=1)
            if res:
                aura_engine.record_task_run("daily_digest")
                logger.info(f"📰 Daily digest saved: {res}")
        except Exception as e:
            logger.error(f"Daily digest generation failed: {e}")
            logger.debug(traceback.format_exc())
    else:
        logger.info("📰 Daily digest already generated today, skipping.")

    # Phase 5: Explore project ideas automatically (Daily idempotent: Once per day)
    project_explore_path = os.path.join(OBSIDIAN_BASE_PATH, "02 项目库_Projects", f"Python自动化项目探索_{today_compact}.md")
    if not os.path.exists(project_explore_path) and aura_engine.should_run_task("project_explorer", interval_days=1):
        try:
            logger.info("🔍 Starting project exploration (first run today)...")
            result = explore_and_save()
            if result:
                aura_engine.record_task_run("project_explorer")
                logger.info(f"🚀 Project exploration complete: {result}")
        except Exception as e:
            logger.error(f"Project exploration failed: {e}")
            logger.debug(traceback.format_exc())
    else:
        logger.info("🔍 Project exploration already generated today, skipping.")

    # Phase 6: Merge similar skills in the library (Periodic: Once every 3 days)
    if aura_engine.should_run_task("skill_merger", interval_days=3):
        try:
            logger.info("🔄 Running periodic skill library deduplication (once every 3 days)...")
            process_skill_merging()
            aura_engine.record_task_run("skill_merger")
        except Exception as e:
            logger.error(f"Skill merging failed: {e}")
            logger.debug(traceback.format_exc())
    else:
        logger.info("🔄 Skill merging was run recently (<3 days), skipping.")

    # Phase 7: Auto-link knowledge cards with [[双链]] (Daily idempotent: Once per day)
    if aura_engine.should_run_task("auto_linker", interval_days=1):
        try:
            logger.info("🌐 Running knowledge graph auto-linking (first run today)...")
            process_auto_linking()
            aura_engine.record_task_run("auto_linker")
        except Exception as e:
            logger.error(f"Auto-linking failed: {e}")
            logger.debug(traceback.format_exc())
    else:
        logger.info("🌐 Knowledge graph auto-linking already ran today, skipping.")

    # Phase 8: Spaced repetition review scheduler (Daily idempotent: Once per day)
    review_path = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每日复习", f"间隔复习_{today_str}.md")
    if not os.path.exists(review_path) and aura_engine.should_run_task("spaced_review", interval_days=1):
        try:
            logger.info("🧠 Running Spaced Repetition Scheduler (first run today)...")
            res = process_spaced_review()
            if res:
                aura_engine.record_task_run("spaced_review")
        except Exception as e:
            logger.error(f"Spaced review failed: {e}")
            logger.debug(traceback.format_exc())
    else:
        logger.info("🧠 SM-2 review checklist already generated today, skipping.")

    # Phase 9: Process answered open questions into Insights
    try:
        logger.info("💡 Scanning for answered Open Questions...")
        process_answered_questions()
    except Exception as e:
        logger.error(f"Open questions processing failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 10: Weekly Cognitive Report (Periodic: Mondays, once per week)
    if datetime.date.today().weekday() == 0 and aura_engine.should_run_task("weekly_report", interval_days=6):
        try:
            logger.info("📅 Today is Monday! Generating Weekly Cognitive Report...")
            generate_weekly_cognitive_report()
            aura_engine.record_task_run("weekly_report")
        except Exception as e:
            logger.error(f"Weekly report generation failed: {e}")
            logger.debug(traceback.format_exc())

    # Phase 12: Digital Lifeform (LAAP) Simulation (Daily idempotent: Once per day)
    laap_card = os.path.join(LAAP_FEEDBACK_DIR, f"🧬 分身推演报告_{today_str}.md")
    if not os.path.exists(laap_card) and aura_engine.should_run_task("laap_simulation", interval_days=1):
        try:
            logger.info("🧬 Running Personal LAAP Agent Forward Simulation (first run today)...")
            run_daily_simulation()
            aura_engine.record_task_run("laap_simulation")
        except Exception as e:
            logger.error(f"LAAP Agent simulation failed: {e}")
            logger.debug(traceback.format_exc())
    else:
        logger.info("🧬 LAAP simulation already generated today, skipping.")

    # Phase 13.5: Auto SDD CodeGen (Only if #SDD_Pending exists)
    try:
        from sdd_agent import auto_process_pending_specs
        auto_process_pending_specs()
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"Auto SDD CodeGen failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 14: Asset Radar
    try:
        process_asset_radar()
    except Exception as e:
        logger.error(f"Asset Radar failed: {e}")
        logger.debug(traceback.format_exc())

    # Phase 15: Polar Star Dashboard (Daily idempotent: Once per day)
    dashboard_path = os.path.join(POLAR_STAR_DIR, "北极星监控看板.md")
    dashboard_updated_today = False
    if os.path.exists(dashboard_path):
        mtime_date = datetime.datetime.fromtimestamp(os.path.getmtime(dashboard_path)).strftime("%Y-%m-%d")
        if mtime_date == today_str:
            dashboard_updated_today = True

    if not dashboard_updated_today and aura_engine.should_run_task("polar_star_dashboard", interval_days=1):
        try:
            logger.info("🧭 Running North Star Dashboard Generator (first run today)...")
            generate_dashboard()
            aura_engine.record_task_run("polar_star_dashboard")
        except Exception as e:
            logger.error(f"North Star Dashboard generation failed: {e}")
            logger.debug(traceback.format_exc())
    else:
        logger.info("🧭 North Star Dashboard already generated today, skipping.")

    logger.info("Obsidian AI Brain Engine Pipeline Finished.")


def start_pipeline_in_background():
    """Run the pipeline immediately in a separate thread so it doesn't block the server startup."""
    threading.Thread(target=run_pipeline, daemon=True).start()

def main():
    logger.info("Starting Obsidian AI Brain Engine with AuraMemory & LAAP Sidecar...")
    
    # 0. Start AuraMemory Engine & Watcher
    aura_engine = get_engine()
    # Register full task pipeline for real-time event-driven processing
    aura_engine.inbox_worker.set_task_processor(process_task)
    try:
        aura_engine.start()
    except Exception as e:
        logger.error(f"Failed to start AuraMemory Engine: {e}")

    
    # 1. Setup Scheduler
    scheduler = BackgroundScheduler()
    # Run pipeline every 2 hours
    scheduler.add_job(run_pipeline, 'interval', hours=2)
    scheduler.start()
    
    # 2. Run pipeline once on startup
    start_pipeline_in_background()
    
    # (Telegram bots are now running separately on Lightsail)
    # 4. Start Unified FastAPI Server (Port 8888)
    logger.info("🚀 Starting Unified AuraMemory & LAAP Server on port 8888...")
    try:
        uvicorn.run(laap_app, host="0.0.0.0", port=8888, log_level="info")
    finally:
        aura_engine.stop()

if __name__ == "__main__":
    main()
