import os
import time
import logging
import threading
from typing import Set, Dict, List, Optional, Any
from contextlib import contextmanager
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .config import (
    WATCH_DIRS,
    INBOX_DIR,
    WATCHER_DEBOUNCE_SECONDS,
    INBOX_DEBOUNCE_SECONDS,
    IGNORE_SUBSTRINGS,
    IGNORE_EXTENSIONS
)
from .parser import parse_markdown_file
from .db import AuraMemoryDB

logger = logging.getLogger(__name__)

class AuraMemoryEventHandler(FileSystemEventHandler):
    """Event handler for Watchdog with debouncing, inbox queue dispatch, and ignore list."""
    
    def __init__(
        self,
        db: AuraMemoryDB,
        debounce_seconds: float = WATCHER_DEBOUNCE_SECONDS,
        inbox_dir: Optional[str] = INBOX_DIR,
        inbox_debounce_seconds: float = INBOX_DEBOUNCE_SECONDS,
        inbox_worker: Optional[Any] = None
    ):
        super().__init__()
        self.db = db
        self.debounce_seconds = debounce_seconds
        self.inbox_dir = os.path.normpath(inbox_dir) if inbox_dir else None
        self.inbox_debounce_seconds = inbox_debounce_seconds
        self.inbox_worker = inbox_worker
        self._debounce_timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._ignored_paths: Set[str] = set()


    @contextmanager
    def ignore_path(self, path: str):
        """Context manager to ignore self-writes or programmatic modifications."""
        norm = os.path.normpath(path)
        with self._lock:
            self._ignored_paths.add(norm)
        try:
            yield
        finally:
            # Keep in ignore list for 1.0s to allow OS event queue to flush
            def cleanup():
                with self._lock:
                    self._ignored_paths.discard(norm)
            threading.Timer(1.0, cleanup).start()

    def _should_ignore(self, path: str) -> bool:
        norm = os.path.normpath(path)
        if not norm.endswith('.md'):
            return True
            
        with self._lock:
            if norm in self._ignored_paths:
                return True
                
        # Check substrings
        lower_norm = norm.lower()
        for sub in IGNORE_SUBSTRINGS:
            if sub.lower() in lower_norm:
                return True
                
        # Check extensions
        for ext in IGNORE_EXTENSIONS:
            if lower_norm.endswith(ext.lower()):
                return True
                
        return False

    def _is_inbox_path(self, path: str) -> bool:
        """Check if path resides within INBOX_DIR."""
        if not self.inbox_dir:
            return False
        norm_path = os.path.normpath(path)
        try:
            return os.path.commonpath([self.inbox_dir, norm_path]) == self.inbox_dir
        except ValueError:
            return False

    def _is_review_checklist_path(self, path: str) -> bool:
        """Check if path is a daily spaced review checklist markdown file."""
        norm_path = os.path.normpath(path)
        base = os.path.basename(norm_path)
        return base.startswith("间隔复习_") and base.endswith(".md")

    def on_created(self, event: FileSystemEvent):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._schedule_debounce(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._schedule_debounce(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        norm = os.path.normpath(event.src_path)
        with self._lock:
            if norm in self._debounce_timers:
                self._debounce_timers[norm].cancel()
                del self._debounce_timers[norm]
        if not self._is_inbox_path(norm) and not self._is_review_checklist_path(norm):
            logger.info(f"🗑️ Watchdog detected deletion: {norm}")
            self.db.delete_record(norm)

    def on_moved(self, event: FileSystemEvent):
        if event.is_directory:
            return
        src_norm = os.path.normpath(event.src_path)
        dest_norm = os.path.normpath(event.dest_path)
        
        # Remove source if not inbox or review checklist
        if not self._is_inbox_path(src_norm) and not self._is_review_checklist_path(src_norm):
            self.db.delete_record(src_norm)
        # Schedule destination
        if not self._should_ignore(dest_norm):
            self._schedule_debounce(dest_norm)

    def _schedule_debounce(self, path: str):
        norm = os.path.normpath(path)
        is_inbox = self._is_inbox_path(norm)
        is_review = self._is_review_checklist_path(norm)
        wait_time = self.inbox_debounce_seconds if is_inbox else self.debounce_seconds
        
        with self._lock:
            if norm in self._debounce_timers:
                self._debounce_timers[norm].cancel()
                
            if is_inbox:
                target_fn = self._process_inbox_debounced
            elif is_review:
                target_fn = self._process_review_debounced
            else:
                target_fn = self._process_file_debounced
                
            timer = threading.Timer(wait_time, target_fn, args=[norm])
            self._debounce_timers[norm] = timer
            timer.start()

    def _process_inbox_debounced(self, file_path: str):
        """Dispatches an inbox markdown file to the InboxWorker after debounce period."""
        with self._lock:
            self._debounce_timers.pop(file_path, None)
            
        if not os.path.exists(file_path):
            return
            
        logger.info(f"📥 Inbox debounced event ready for dispatch: {file_path}")
        if self.inbox_worker:
            self.inbox_worker.enqueue(file_path)

    def _process_review_debounced(self, file_path: str):
        """Dispatches a review checklist note to process checked cards after debounce period."""
        with self._lock:
            self._debounce_timers.pop(file_path, None)
            
        if not os.path.exists(file_path):
            return
            
        try:
            try:
                from ..spaced_review import process_checklist_completions
            except (ImportError, ValueError):
                from src.spaced_review import process_checklist_completions
                
            completed = process_checklist_completions(
                review_file_path=file_path,
                today=None,
                db=self.db,
                watcher_handler=self
            )
            if completed > 0:
                logger.info(f"🎯 Watchdog auto-processed {completed} reviewed cards from checklist: {file_path}")
        except Exception as e:
            logger.error(f"Error in debounced review processor for {file_path}: {e}")

    def _process_file_debounced(self, file_path: str):
        with self._lock:
            self._debounce_timers.pop(file_path, None)
            
        if not os.path.exists(file_path):
            return
            
        try:
            record = parse_markdown_file(file_path)
            if record:
                self.db.upsert_record(record)
                logger.info(f"⚡ AuraMemory Watchdog synced note: {record.title} ({record.category})")
            else:
                logger.warning(f"Could not parse note from {file_path}")
        except Exception as e:
            logger.error(f"Error in debounced file processor for {file_path}: {e}")

class AuraMemoryWatcher:
    """Orchestrates Watchdog observer for all monitored Obsidian directories."""
    
    def __init__(
        self,
        db: AuraMemoryDB,
        watch_dirs: Optional[List[str]] = None,
        inbox_worker: Optional[Any] = None,
        inbox_dir: Optional[str] = INBOX_DIR,
        inbox_debounce_seconds: float = INBOX_DEBOUNCE_SECONDS
    ):
        self.db = db
        self.watch_dirs = list(watch_dirs or WATCH_DIRS)
        if inbox_dir and inbox_dir not in self.watch_dirs:
            self.watch_dirs.append(inbox_dir)
            
        self.handler = AuraMemoryEventHandler(
            db=self.db,
            debounce_seconds=WATCHER_DEBOUNCE_SECONDS,
            inbox_dir=inbox_dir,
            inbox_debounce_seconds=inbox_debounce_seconds,
            inbox_worker=inbox_worker
        )
        self.observer = Observer()
        self._is_running = False


    def start(self):
        """Start monitoring configured directories."""
        if self._is_running:
            return
            
        active_watches = 0
        for directory in self.watch_dirs:
            if os.path.exists(directory):
                self.observer.schedule(self.handler, path=directory, recursive=True)
                logger.info(f"👀 AuraMemory Watcher scheduled for: {directory}")
                active_watches += 1
            else:
                logger.warning(f"Watch directory does not exist, skipping: {directory}")
                
        if active_watches > 0:
            self.observer.start()
            self._is_running = True
            logger.info(f"🚀 AuraMemory Watcher started with {active_watches} active watch directories.")
        else:
            logger.warning("No valid directories found to watch for AuraMemory.")

    def stop(self):
        """Stop watchdog observer cleanly."""
        if self._is_running:
            self.observer.stop()
            self.observer.join(timeout=5)
            self._is_running = False
            logger.info("🛑 AuraMemory Watcher stopped.")
