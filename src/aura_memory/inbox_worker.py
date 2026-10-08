import os
import queue
import logging
import threading
from typing import Optional, Callable, Dict, Any, List
from .config import INBOX_DIR, SKILLS_DIR

logger = logging.getLogger(__name__)

class InboxWorker:
    """
    Event-driven FIFO background task worker for processing items dropped into Inbox.
    Uses single-threaded serial execution to prevent overload and API rate limits.
    Wraps writes with watcher ignore_path to prevent recursive file events.
    """

    def __init__(self, watcher_handler=None, task_processor: Optional[Callable[[Dict[str, Any]], bool]] = None):
        self.queue: queue.Queue[str] = queue.Queue()
        self.watcher_handler = watcher_handler
        self.task_processor = task_processor
        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._processed_count = 0
        self._last_processed_file: Optional[str] = None
        self._last_error: Optional[str] = None

    def set_task_processor(self, processor: Callable[[Dict[str, Any]], bool]):
        """Register custom task processor (e.g., from main.py)."""
        self.task_processor = processor

    def enqueue(self, file_path: str):
        """Enqueue an inbox file for task processing."""
        if not file_path or not file_path.endswith('.md'):
            return
        logger.info(f"📥 InboxWorker enqueued file: {file_path}")
        self.queue.put(file_path)

    def start(self):
        """Start the background worker thread."""
        if self._is_running:
            return
        self._is_running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="AuraInboxWorker")
        self._worker_thread.start()
        logger.info("🚀 AuraMemory InboxWorker started.")

    def stop(self):
        """Stop worker cleanly."""
        if not self._is_running:
            return
        self._is_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3)
        logger.info("🛑 AuraMemory InboxWorker stopped.")

    def _worker_loop(self):
        """Continuously consume files from the queue."""
        while self._is_running:
            try:
                file_path = self.queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                self._process_file(file_path)
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"Error in InboxWorker processing {file_path}: {e}", exc_info=True)
            finally:
                self.queue.task_done()

    def _process_file(self, file_path: str):
        """Scan file for pending tasks and execute them."""
        norm_path = os.path.normpath(file_path)
        if not os.path.exists(norm_path):
            return

        try:
            from scheduler import scan_inbox_file
        except ImportError:
            try:
                from src.scheduler import scan_inbox_file
            except ImportError:
                import sys
                sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
                from scheduler import scan_inbox_file

        tasks = scan_inbox_file(norm_path)

        if not tasks:
            logger.debug(f"No pending tasks found in {norm_path}")
            return

        logger.info(f"⚡ InboxWorker found {len(tasks)} pending tasks in {os.path.basename(norm_path)}")

        for task in tasks:
            # Self-write ignore lock: ensure file updates do NOT re-trigger the watcher
            if self.watcher_handler and hasattr(self.watcher_handler, 'ignore_path'):
                with self.watcher_handler.ignore_path(norm_path):
                    self._execute_single_task(task)
            else:
                self._execute_single_task(task)

        self._processed_count += len(tasks)
        self._last_processed_file = norm_path

    def _execute_single_task(self, task: Dict[str, Any]) -> bool:
        """Execute a single task using the registered processor or fallback to Feynman Juicer."""
        if self.task_processor:
            try:
                return self.task_processor(task)
            except Exception as e:
                logger.error(f"Task processor failed: {e}", exc_info=True)
                return False

        # Fallback processor: directly invoke Feynman Juicer or scheduler
        return self._default_task_processor(task)

    def _default_task_processor(self, task: Dict[str, Any]) -> bool:
        """Fallback processor using feynman_juicer or marking completed."""
        file_path = task['file_path']
        payload = task['payload']
        logger.info(f"Executing fallback task processor for: {payload}")

        import re
        url_match = re.search(r'(https?://[^\s\>\]\)]+)', payload)
        target_url = url_match.group(1) if url_match else None

        if target_url:
            try:
                from feynman_juicer.media_extractor import MediaExtractor
                from feynman_juicer.juicer_engine import JuicerEngine
                from scheduler import mark_task_completed
            except ImportError:
                from src.feynman_juicer.media_extractor import MediaExtractor
                from src.feynman_juicer.juicer_engine import JuicerEngine
                from src.scheduler import mark_task_completed
            try:
                extractor = MediaExtractor()
                engine = JuicerEngine()
                audio_path = extractor.download_audio(target_url)
                data = engine.juice_audio(audio_path)
                md_content = engine.render_obsidian_card(data, target_url)
                
                safe_title = "".join(c for c in data.get('title', 'Untitled') if c.isalnum() or c in (' ', '-', '_')).strip()
                out_file = os.path.join(SKILLS_DIR, f"{safe_title}.md")
                os.makedirs(os.path.dirname(out_file), exist_ok=True)
                
                with open(out_file, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                    
                mark_task_completed(file_path, task['original_line'])
                logger.info(f"✅ Juiced skill card saved to {out_file}")
                return True
            except Exception as e:
                logger.error(f"Feynman Juicer processing failed for {target_url}: {e}")
                return False
        else:
            try:
                from scheduler import mark_task_completed
            except ImportError:
                from src.scheduler import mark_task_completed
            return mark_task_completed(file_path, task['original_line'])


    def get_status(self) -> Dict[str, Any]:
        """Return worker runtime stats."""
        return {
            "is_running": self._is_running,
            "queue_size": self.queue.qsize(),
            "processed_count": self._processed_count,
            "last_processed_file": self._last_processed_file,
            "last_error": self._last_error
        }
