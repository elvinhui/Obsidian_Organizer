from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import datetime

class MemoryRecord(BaseModel):
    """Core bi-temporal memory record representing an Obsidian note."""
    note_id: str
    file_path: str
    title: str
    category: str = "skills"
    frontmatter: Dict[str, Any] = Field(default_factory=dict)
    content_text: str = ""
    
    # Bi-temporal timestamps
    real_effect_time: str  # YYYY-MM-DD or ISO string representing when knowledge became real/effective
    sys_write_time: str    # ISO string representing system perception / file mtime
    effective_until: Optional[str] = None  # None or 9999-12-31 if permanently active
    superseded_by: Optional[str] = None   # Note ID/Path that replaced this knowledge
    
    # SM-2 and cognitive metadata
    sm2_ease: float = 2.5
    sm2_interval: int = 0
    sm2_next_review: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    updated_at: Optional[str] = None

class QueryRequest(BaseModel):
    """Natural query or keyword search request with temporal constraints."""
    query: Optional[str] = None
    category: Optional[str] = None
    as_of: Optional[str] = None  # YYYY-MM-DD. Defaults to current date if None.
    tags: Optional[List[str]] = None
    include_superseded: bool = False
    limit: int = 20

class QueryResponseItem(BaseModel):
    """Single search result item."""
    note_id: str
    file_path: str
    title: str
    category: str
    real_effect_time: str
    sys_write_time: str
    sm2_next_review: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    snippet: str = ""
    rank: Optional[float] = None
    is_superseded: bool = False

class QueryResponse(BaseModel):
    """Envelope for temporal query results."""
    query: Optional[str] = None
    as_of: str
    count: int
    results: List[QueryResponseItem]

class DueReviewItem(BaseModel):
    """Card due for SM-2 spaced review."""
    title: str
    file_path: str
    category: str
    sm2_ease: float
    sm2_interval: int
    sm2_next_review: str

class DueReviewResponse(BaseModel):
    """Response containing due cards."""
    target_date: str
    count: int
    due_cards: List[DueReviewItem]

class ProfileView(BaseModel):
    """Materialized snapshot view of current user state and knowledge landscape."""
    generated_at: str
    active_projects: List[Dict[str, Any]] = Field(default_factory=list)
    recent_skills: List[Dict[str, Any]] = Field(default_factory=list)
    recent_insights: List[Dict[str, Any]] = Field(default_factory=list)
    due_reviews_count: int = 0
    total_records: int = 0

class HistoryItem(BaseModel):
    """Audit snapshot of a previous version of a memory record."""
    id: int
    ledger_id: int
    file_path: str
    note_id: str
    title: str
    category: str
    frontmatter: Dict[str, Any] = Field(default_factory=dict)
    content_text: str = ""
    real_effect_time: str
    sys_write_time: str
    effective_until: Optional[str] = None
    superseded_by: Optional[str] = None
    recorded_at: str

class HistoryResponse(BaseModel):
    """Response envelope for audit history of a card."""
    note_id: Optional[str] = None
    file_path: Optional[str] = None
    count: int
    history: List[HistoryItem]

