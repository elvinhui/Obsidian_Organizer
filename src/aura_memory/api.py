from typing import Optional, List, Dict, Any
from fastapi import FastAPI, APIRouter, BackgroundTasks, Query
from .engine import get_engine, AuraMemoryEngine
from .schema import (
    QueryRequest,
    QueryResponse,
    ProfileView,
    DueReviewResponse,
    DueReviewItem,
    HistoryResponse,
    HistoryItem
)

router = APIRouter(prefix="/memory", tags=["AuraMemory"])

@router.get("/history", response_model=HistoryResponse)
def get_memory_history(
    file_path: Optional[str] = Query(None, description="Absolute or relative file path of the note"),
    note_id: Optional[str] = Query(None, description="Unique note ID")
):
    """
    Retrieve the bi-temporal audit trail and historical revisions of a specific note.
    """
    engine = get_engine()
    raw_history = engine.get_history(file_path=file_path, note_id=note_id)
    items = [HistoryItem(**item) for item in raw_history]
    return HistoryResponse(
        note_id=note_id,
        file_path=file_path,
        count=len(items),
        history=items
    )

@router.post("/query", response_model=QueryResponse)
def query_memory(request: QueryRequest):

    """
    Search memories with full-text search and bi-temporal constraints.
    Supports time travel using the `as_of` parameter.
    """
    engine = get_engine()
    return engine.query(request)

@router.get("/profile", response_model=ProfileView)
def get_user_profile():
    """
    Returns the real-time materialized user profile and landscape view.
    Includes active projects, recent skills, and due reviews count.
    """
    engine = get_engine()
    return engine.get_profile()

@router.get("/reviews/due", response_model=DueReviewResponse)
def get_due_reviews(
    target_date: Optional[str] = Query(None, description="Target review date YYYY-MM-DD (defaults to today)"),
    categories: Optional[List[str]] = Query(None, description="Categories to include (defaults to skills and insights, excluding projects)")
):
    """
    Returns knowledge cards due for spaced repetition review (defaults to skills and insights, excluding projects).
    """
    engine = get_engine()
    cats = categories if categories is not None else ["skills", "insights"]
    cards = engine.get_due_reviews(target_date, categories=cats)
    import datetime
    effective_target = target_date or datetime.date.today().strftime("%Y-%m-%d")
    return DueReviewResponse(
        target_date=effective_target,
        count=len(cards),
        due_cards=cards
    )

@router.post("/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    """
    Triggers a full re-scan and sync of all monitored Obsidian directories.
    """
    engine = get_engine()
    background_tasks.add_task(engine.sync_all)
    return {"message": "AuraMemory synchronization triggered in background."}

@router.get("/stats")
def get_memory_stats():
    """
    Returns summary statistics of the memory ledger and SQLite database.
    """
    engine = get_engine()
    return engine.get_stats()

@router.get("/inbox/status")
def get_inbox_status():
    """
    Returns runtime status of the event-driven Inbox FIFO worker.
    """
    engine = get_engine()
    return engine.get_inbox_status()

@router.get("/health")
def health_check():
    """
    Health check endpoint reporting engine status and active watcher state.
    """
    engine = get_engine()
    return {
        "status": "healthy",
        "watcher_running": engine.watcher._is_running,
        "inbox_worker_running": engine.inbox_worker._is_running,
        "monitored_directories": engine.watch_dirs
    }


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    engine.start()
    yield
    engine.stop()

# Standalone App Instance
app = FastAPI(title="AuraMemory-Engine Internal API", lifespan=lifespan)
app.include_router(router)
