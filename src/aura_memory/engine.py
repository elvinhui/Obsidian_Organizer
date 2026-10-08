import os
import glob
import time
import logging
from typing import Optional, List, Dict, Any
from .config import WATCH_DIRS, INBOX_DIR, REVIEW_DIR, AURA_DB_PATH
from .db import AuraMemoryDB
from .parser import parse_markdown_file
from .watcher import AuraMemoryWatcher
from .inbox_worker import InboxWorker
from .schema import QueryRequest, QueryResponse, ProfileView, DueReviewItem

logger = logging.getLogger(__name__)

class AuraMemoryEngine:
    """Core coordinator for AuraMemory: DB, Watcher, InboxWorker, Indexing, and Query Views."""
    
    def __init__(self, db_path: str = AURA_DB_PATH, watch_dirs: Optional[List[str]] = None):
        self.db = AuraMemoryDB(db_path=db_path)
        self.watch_dirs = list(watch_dirs or WATCH_DIRS)
        self.inbox_worker = InboxWorker()
        self.watcher = AuraMemoryWatcher(
            db=self.db,
            watch_dirs=self.watch_dirs,
            inbox_worker=self.inbox_worker
        )
        self.inbox_worker.watcher_handler = self.watcher.handler
        self._is_started = False

    def sync_all(self, target_dirs: Optional[List[str]] = None) -> Dict[str, Any]:
        """Perform a full scan and synchronization across monitored directories (skipping Inbox and Review Checklists)."""
        skip_dirs = {os.path.normpath(INBOX_DIR), os.path.normpath(REVIEW_DIR)}
        dirs_to_scan = target_dirs or [d for d in self.watch_dirs if os.path.normpath(d) not in skip_dirs]
        start_time = time.time()
        synced_count = 0
        failed_count = 0
        
        logger.info(f"🔄 Starting full AuraMemory synchronization across {len(dirs_to_scan)} directories...")
        
        for directory in dirs_to_scan:
            if not os.path.exists(directory):
                logger.warning(f"Scan directory not found: {directory}")
                continue
            
            dir_name = os.path.basename(directory)
            logger.info(f"📂 Scanning directory: {dir_name} ({directory})...")
            dir_synced = 0
                
            for root, _, files in os.walk(directory):
                for f in files:
                    if f.endswith('.md'):
                        full_path = os.path.join(root, f)
                        # Check ignore substrings
                        if any(ign in full_path for ign in [".obsidian", ".trash", ".git"]):
                            continue
                        try:
                            record = parse_markdown_file(full_path)
                            if record:
                                self.db.upsert_record(record)
                                synced_count += 1
                                dir_synced += 1
                                if synced_count % 20 == 0:
                                    logger.info(f"  ⚡ [AuraMemory] Synced {synced_count} notes so far...")
                            else:
                                failed_count += 1
                        except Exception as e:
                            logger.error(f"Failed to sync file {full_path}: {e}")
                            failed_count += 1
                            
            logger.info(f"  ✓ Finished {dir_name}: {dir_synced} notes indexed.")
                            
        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(f"✅ AuraMemory Sync complete: {synced_count} synced, {failed_count} failed in {duration_ms}ms")
        
        return {
            "synced": synced_count,
            "failed": failed_count,
            "duration_ms": duration_ms
        }

    def start(self, auto_sync_if_empty: bool = True):
        """Start the engine, file system watcher, and inbox worker."""
        if self._is_started:
            return
            
        stats = self.db.get_stats()
        if auto_sync_if_empty and stats.get("total_records", 0) == 0:
            logger.info("AuraMemory DB is empty. Performing initial scan...")
            self.sync_all()
            
        self.inbox_worker.start()
        self.watcher.start()
        self._is_started = True
        logger.info("✨ AuraMemory Engine started successfully.")

    def stop(self):
        """Stop the engine, watcher, and inbox worker."""
        if self._is_started:
            self.watcher.stop()
            self.inbox_worker.stop()
            self._is_started = False
            logger.info("🛑 AuraMemory Engine stopped.")


    def query(self, req: QueryRequest) -> QueryResponse:
        return self.db.query_temporal(req)

    def get_profile(self) -> ProfileView:
        return self.db.get_profile_view()

    def get_due_reviews(self, target_date: Optional[str] = None, categories: Optional[List[str]] = None) -> List[DueReviewItem]:
        return self.db.get_due_reviews(target_date, categories=categories)

    def get_stats(self) -> Dict[str, Any]:
        return self.db.get_stats()

    def get_history(self, file_path: Optional[str] = None, note_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.db.get_card_history(file_path=file_path, note_id=note_id)

    def get_inbox_status(self) -> Dict[str, Any]:
        return self.inbox_worker.get_status()

    def should_run_task(self, task_name: str, interval_days: int = 1) -> bool:
        return self.db.should_run_task(task_name, interval_days)

    def record_task_run(self, task_name: str, status: str = "success"):
        self.db.record_task_run(task_name, status)





# Global Singleton
_global_engine: Optional[AuraMemoryEngine] = None

def get_engine() -> AuraMemoryEngine:
    global _global_engine
    if _global_engine is None:
        _global_engine = AuraMemoryEngine()
    return _global_engine
