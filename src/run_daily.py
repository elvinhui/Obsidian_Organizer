"""
Standalone Daily Execution Runner for Obsidian AI Brain.
Designed for Linux Crontab (e.g. `0 6 * * * python src/run_daily.py`)
or one-shot headless execution on AWS EC2 / Lightsail.
"""
import os
import sys
import logging
import datetime

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.main import run_pipeline
from src.aura_memory.engine import get_engine

logger = logging.getLogger("run_daily")

def main():
    start_time = datetime.datetime.now()
    logger.info(f"🚀 Starting daily knowledge execution cycle at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 1. Sync AuraMemory records from vault
        engine = get_engine()
        sync_res = engine.sync_all()
        logger.info(f"📊 Vault synced: {sync_res.get('synced', 0)} files updated, {sync_res.get('failed', 0)} failed.")
        
        # 2. Run the full processing pipeline
        run_pipeline()
        
        elapsed = (datetime.datetime.now() - start_time).total_seconds()
        logger.info(f"✅ Daily knowledge cycle completed successfully in {elapsed:.2f}s.")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"❌ Daily knowledge execution cycle failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
