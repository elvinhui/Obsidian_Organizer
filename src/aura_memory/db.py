import sqlite3
import json
import os
import datetime
import logging
import threading
import re
from typing import Optional, List, Dict, Any, Tuple
from .config import AURA_DB_PATH
from .schema import MemoryRecord, QueryRequest, QueryResponse, QueryResponseItem, ProfileView, DueReviewItem

logger = logging.getLogger(__name__)

def cjk_tokenize(text: str) -> str:
    """Insert space before and after CJK characters for universal FTS tokenization."""
    if not text:
        return ""
    return re.sub(r'([\u4e00-\u9fa5])', r' \1 ', str(text))

def build_fts_query(query: str) -> str:
    """Convert natural search query into robust FTS phrase/term query."""
    terms = query.strip().split()
    phrases = []
    for term in terms:
        if any('\u4e00' <= c <= '\u9fa5' for c in term):
            spaced = " ".join([c if '\u4e00' <= c <= '\u9fa5' else c for c in term])
            clean_spaced = re.sub(r'(?<=[^\u4e00-\u9fa5\s])\s+(?=[^\u4e00-\u9fa5\s])', '', spaced).strip()
            if clean_spaced:
                phrases.append(f'"{clean_spaced}"')
        else:
            clean_term = term.replace('"', '').strip()
            if clean_term:
                phrases.append(f'"{clean_term}"')
    return " AND ".join(phrases) if phrases else '""'

class AuraMemoryDB:
    def __init__(self, db_path: str = AURA_DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self):
        """Initialize database schema, indexes, and FTS5 tables."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Main Ledger Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memory_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    note_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    frontmatter_json TEXT,
                    content_text TEXT,
                    real_effect_time TEXT NOT NULL,
                    sys_write_time TEXT NOT NULL,
                    effective_until TEXT,
                    superseded_by TEXT,
                    sm2_ease REAL DEFAULT 2.5,
                    sm2_interval INTEGER DEFAULT 0,
                    sm2_next_review TEXT,
                    tags_json TEXT,
                    updated_at TEXT
                );
            ''')
            
            # Indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ledger_note_id ON memory_ledger(note_id);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ledger_temporal ON memory_ledger(real_effect_time, effective_until);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ledger_sm2 ON memory_ledger(sm2_next_review);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ledger_category ON memory_ledger(category);')
            
            # 2. FTS5 Virtual Table for full-text search
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    title,
                    content_text,
                    tags,
                    tokenize = 'unicode61'
                );
            ''')
            
            # 3. Bi-Temporal Audit History Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ledger_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    frontmatter_json TEXT,
                    content_text TEXT,
                    real_effect_time TEXT NOT NULL,
                    sys_write_time TEXT NOT NULL,
                    effective_until TEXT,
                    superseded_by TEXT,
                    recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_note_id ON memory_history(note_id);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_file_path ON memory_history(file_path);')
            
            # 4. Task Execution Ledger for Daily/Periodic Idempotency
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_execution_ledger (
                    task_name TEXT PRIMARY KEY,
                    last_run_date TEXT NOT NULL,
                    last_run_time TEXT NOT NULL,
                    status TEXT NOT NULL
                );
            ''')
            
            conn.commit()
            logger.info(f"AuraMemory DB initialized at {self.db_path}")


    def upsert_record(self, record: MemoryRecord) -> int:
        """Insert or update a memory record into the ledger and update FTS5."""
        tags_str = " ".join(record.tags)
        new_fm_json = json.dumps(record.frontmatter, ensure_ascii=False, default=str)
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check existing row
            cursor.execute("SELECT id FROM memory_ledger WHERE file_path = ?", (record.file_path,))
            row = cursor.fetchone()
            existing_id = row['id'] if row else None
            
            if existing_id:
                # Fetch existing row to check if snapshot into memory_history is needed
                cursor.execute("SELECT * FROM memory_ledger WHERE id = ?", (existing_id,))
                old_row = cursor.fetchone()
                
                # If content, frontmatter, or title changed, save prior version to memory_history
                if old_row and (
                    old_row['content_text'] != record.content_text or
                    old_row['frontmatter_json'] != new_fm_json or
                    old_row['title'] != record.title
                ):
                    cursor.execute('''
                        INSERT INTO memory_history (
                            ledger_id, file_path, note_id, title, category,
                            frontmatter_json, content_text, real_effect_time,
                            sys_write_time, effective_until, superseded_by
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        old_row['id'],
                        old_row['file_path'],
                        old_row['note_id'],
                        old_row['title'],
                        old_row['category'],
                        old_row['frontmatter_json'],
                        old_row['content_text'],
                        old_row['real_effect_time'],
                        old_row['sys_write_time'],
                        record.real_effect_time,
                        record.note_id
                    ))

                # Update ledger
                cursor.execute('''
                    UPDATE memory_ledger SET
                        note_id = ?,
                        title = ?,
                        category = ?,
                        frontmatter_json = ?,
                        content_text = ?,
                        real_effect_time = ?,
                        sys_write_time = ?,
                        effective_until = ?,
                        superseded_by = ?,
                        sm2_ease = ?,
                        sm2_interval = ?,
                        sm2_next_review = ?,
                        tags_json = ?,
                        updated_at = ?
                    WHERE id = ?
                ''', (
                    record.note_id,
                    record.title,
                    record.category,
                    new_fm_json,
                    record.content_text,
                    record.real_effect_time,
                    record.sys_write_time,
                    record.effective_until,
                    record.superseded_by,
                    record.sm2_ease,
                    record.sm2_interval,
                    record.sm2_next_review,
                    json.dumps(record.tags, ensure_ascii=False, default=str),
                    record.updated_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    existing_id
                ))
                record_id = existing_id
                # Update FTS
                cursor.execute("DELETE FROM memory_fts WHERE rowid = ?", (record_id,))
                cursor.execute(
                    "INSERT INTO memory_fts(rowid, title, content_text, tags) VALUES (?, ?, ?, ?)",
                    (record_id, cjk_tokenize(record.title), cjk_tokenize(record.content_text), cjk_tokenize(tags_str))
                )
            else:
                # Insert new record using ON CONFLICT for atomic concurrency safety
                cursor.execute('''
                    INSERT INTO memory_ledger (
                        file_path, note_id, title, category, frontmatter_json, content_text,
                        real_effect_time, sys_write_time, effective_until, superseded_by,
                        sm2_ease, sm2_interval, sm2_next_review, tags_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(file_path) DO UPDATE SET
                        note_id = excluded.note_id,
                        title = excluded.title,
                        category = excluded.category,
                        frontmatter_json = excluded.frontmatter_json,
                        content_text = excluded.content_text,
                        real_effect_time = excluded.real_effect_time,
                        sys_write_time = excluded.sys_write_time,
                        effective_until = excluded.effective_until,
                        superseded_by = excluded.superseded_by,
                        sm2_ease = excluded.sm2_ease,
                        sm2_interval = excluded.sm2_interval,
                        sm2_next_review = excluded.sm2_next_review,
                        tags_json = excluded.tags_json,
                        updated_at = excluded.updated_at
                ''', (
                    record.file_path,
                    record.note_id,
                    record.title,
                    record.category,
                    new_fm_json,
                    record.content_text,
                    record.real_effect_time,
                    record.sys_write_time,
                    record.effective_until,
                    record.superseded_by,
                    record.sm2_ease,
                    record.sm2_interval,
                    record.sm2_next_review,
                    json.dumps(record.tags, ensure_ascii=False, default=str),
                    record.updated_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                cursor.execute("SELECT id FROM memory_ledger WHERE file_path = ?", (record.file_path,))
                r = cursor.fetchone()
                record_id = r['id'] if r else cursor.lastrowid
                cursor.execute("DELETE FROM memory_fts WHERE rowid = ?", (record_id,))
                cursor.execute(
                    "INSERT INTO memory_fts(rowid, title, content_text, tags) VALUES (?, ?, ?, ?)",
                    (record_id, cjk_tokenize(record.title), cjk_tokenize(record.content_text), cjk_tokenize(tags_str))
                )
                
            conn.commit()
            return record_id

    def delete_record(self, file_path: str) -> bool:
        """Remove a record by file path from both ledger and FTS5."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM memory_ledger WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if not row:
                return False
            record_id = row['id']
            cursor.execute("DELETE FROM memory_ledger WHERE id = ?", (record_id,))
            cursor.execute("DELETE FROM memory_fts WHERE rowid = ?", (record_id,))
            conn.commit()
            return True

    def query_temporal(self, req: QueryRequest) -> QueryResponse:
        """
        Execute temporal search: FTS5 matching + Bi-temporal slice filtering.
        """
        as_of = req.as_of or datetime.date.today().strftime("%Y-%m-%d")
        params: List[Any] = []
        where_clauses: List[str] = []
        
        # 1. Bi-temporal conditions:
        # Knowledge must have taken effect on or before as_of
        where_clauses.append("l.real_effect_time <= ?")
        params.append(as_of)
        
        # Unless superseded records are explicitly requested, exclude expired/superseded ones
        if not req.include_superseded:
            where_clauses.append("((l.effective_until IS NOT NULL AND l.effective_until >= ?) OR (l.effective_until IS NULL AND (l.superseded_by IS NULL OR l.superseded_by = '')))")
            params.append(as_of)
            
        # 2. Category filter
        if req.category:
            where_clauses.append("l.category = ?")
            params.append(req.category)
            
        # 3. Tags filter
        if req.tags:
            for tag in req.tags:
                where_clauses.append("l.tags_json LIKE ?")
                params.append(f'%"{tag}"%')

        clean_query = req.query.strip() if req.query else ""
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if clean_query:
                # Sanitize and convert FTS5 query string
                sanitized_fts = build_fts_query(clean_query)
                
                where_clauses.append("memory_fts MATCH ?")
                params.append(sanitized_fts)
                
                where_sql = " AND ".join(where_clauses)
                sql = f'''
                    SELECT 
                        l.id, l.note_id, l.file_path, l.title, l.category,
                        l.real_effect_time, l.sys_write_time, l.effective_until, l.superseded_by,
                        l.sm2_next_review, l.tags_json, l.content_text,
                        memory_fts.rank
                    FROM memory_fts
                    JOIN memory_ledger l ON memory_fts.rowid = l.id
                    WHERE {where_sql}
                    ORDER BY memory_fts.rank ASC, l.real_effect_time DESC
                    LIMIT ?
                '''
                params.append(req.limit)
            else:
                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
                sql = f'''
                    SELECT 
                        l.id, l.note_id, l.file_path, l.title, l.category,
                        l.real_effect_time, l.sys_write_time, l.effective_until, l.superseded_by,
                        l.sm2_next_review, l.tags_json, l.content_text,
                        NULL as rank
                    FROM memory_ledger l
                    WHERE {where_sql}
                    ORDER BY l.real_effect_time DESC
                    LIMIT ?
                '''
                params.append(req.limit)
                
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results: List[QueryResponseItem] = []
            for r in rows:
                tags = json.loads(r['tags_json']) if r['tags_json'] else []
                # Snippet: first 200 chars
                snippet = (r['content_text'] or "")[:200].replace("\n", " ").strip()
                is_superseded = bool(r['superseded_by'] or (r['effective_until'] and r['effective_until'] < as_of))
                results.append(QueryResponseItem(
                    note_id=r['note_id'],
                    file_path=r['file_path'],
                    title=r['title'],
                    category=r['category'],
                    real_effect_time=r['real_effect_time'],
                    sys_write_time=r['sys_write_time'],
                    sm2_next_review=r['sm2_next_review'],
                    tags=tags,
                    snippet=snippet,
                    rank=r['rank'],
                    is_superseded=is_superseded
                ))
                
            return QueryResponse(
                query=req.query,
                as_of=as_of,
                count=len(results),
                results=results
            )

    def get_due_reviews(self, target_date: Optional[str] = None, categories: Optional[List[str]] = None) -> List[DueReviewItem]:
        """Fetch all cards due for SM-2 review on or before target_date. Defaults to skills and insights, excluding projects."""
        if not target_date:
            target_date = datetime.date.today().strftime("%Y-%m-%d")
            
        cats = categories if categories is not None else ["skills", "insights"]
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if cats:
                placeholders = ','.join('?' for _ in cats)
                cursor.execute(f'''
                    SELECT title, file_path, category, sm2_ease, sm2_interval, sm2_next_review
                    FROM memory_ledger
                    WHERE sm2_next_review IS NOT NULL 
                      AND sm2_next_review <= ?
                      AND category IN ({placeholders})
                      AND title NOT LIKE '[已合并]%'
                    ORDER BY sm2_next_review ASC
                ''', [target_date, *cats])
            else:
                cursor.execute('''
                    SELECT title, file_path, category, sm2_ease, sm2_interval, sm2_next_review
                    FROM memory_ledger
                    WHERE sm2_next_review IS NOT NULL 
                      AND sm2_next_review <= ?
                      AND title NOT LIKE '[已合并]%'
                    ORDER BY sm2_next_review ASC
                ''', (target_date,))
                
            rows = cursor.fetchall()
            
            due_items = []
            for r in rows:
                due_items.append(DueReviewItem(
                    title=r['title'],
                    file_path=r['file_path'],
                    category=r['category'],
                    sm2_ease=r['sm2_ease'],
                    sm2_interval=r['sm2_interval'],
                    sm2_next_review=r['sm2_next_review']
                ))
            return due_items

    def get_profile_view(self) -> ProfileView:
        """Generate real-time materialized user profile and landscape view."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Active Projects
            cursor.execute('''
                SELECT note_id, title, real_effect_time, tags_json, content_text
                FROM memory_ledger
                WHERE category = 'projects'
                  AND real_effect_time <= ?
                  AND (effective_until IS NULL OR effective_until >= ?)
                  AND (superseded_by IS NULL OR superseded_by = '')
                ORDER BY real_effect_time DESC
                LIMIT 10
            ''', (today, today))
            active_projects = [
                {
                    "title": r['title'],
                    "note_id": r['note_id'],
                    "date": r['real_effect_time'],
                    "tags": json.loads(r['tags_json']) if r['tags_json'] else [],
                    "summary": (r['content_text'] or "")[:150].strip()
                }
                for r in cursor.fetchall()
            ]
            
            # Recent Skills
            cursor.execute('''
                SELECT note_id, title, real_effect_time, tags_json
                FROM memory_ledger
                WHERE category = 'skills'
                ORDER BY real_effect_time DESC
                LIMIT 10
            ''')
            recent_skills = [
                {
                    "title": r['title'],
                    "note_id": r['note_id'],
                    "date": r['real_effect_time'],
                    "tags": json.loads(r['tags_json']) if r['tags_json'] else []
                }
                for r in cursor.fetchall()
            ]
            
            # Recent Insights
            cursor.execute('''
                SELECT note_id, title, real_effect_time, tags_json
                FROM memory_ledger
                WHERE category = 'insights'
                ORDER BY real_effect_time DESC
                LIMIT 10
            ''')
            recent_insights = [
                {
                    "title": r['title'],
                    "note_id": r['note_id'],
                    "date": r['real_effect_time'],
                    "tags": json.loads(r['tags_json']) if r['tags_json'] else []
                }
                for r in cursor.fetchall()
            ]
            
            # Due review count (skills and insights only, excluding merged)
            cursor.execute("SELECT COUNT(*) FROM memory_ledger WHERE sm2_next_review <= ? AND category IN ('skills', 'insights') AND title NOT LIKE '[已合并]%'", (today,))
            due_count = cursor.fetchone()[0]
            
            # Total count
            cursor.execute('SELECT COUNT(*) FROM memory_ledger')
            total_count = cursor.fetchone()[0]
            
            return ProfileView(
                generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                active_projects=active_projects,
                recent_skills=recent_skills,
                recent_insights=recent_insights,
                due_reviews_count=due_count,
                total_records=total_count
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics of the memory ledger."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT category, COUNT(*) as count FROM memory_ledger GROUP BY category')
            categories = {r['category']: r['count'] for r in cursor.fetchall()}
            
            cursor.execute('SELECT COUNT(*) FROM memory_ledger')
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM memory_ledger WHERE sm2_next_review <= ? AND category IN ('skills', 'insights') AND title NOT LIKE '[已合并]%'", (today,))
            due_reviews = cursor.fetchone()[0]
            
            return {
                "total_records": total,
                "due_reviews_today": due_reviews,
                "categories": categories,
                "database_path": self.db_path
            }

    def get_card_history(self, file_path: Optional[str] = None, note_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve audit trail of historical versions for a specific card."""
        if not file_path and not note_id:
            return []
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []
            if file_path:
                norm_path = os.path.normpath(file_path)
                conditions.append("(file_path = ? OR file_path LIKE ?)")
                params.extend([norm_path, f"%{os.path.basename(file_path)}"])
            if note_id:
                conditions.append("note_id = ?")
                params.append(note_id)
                
            query = f"""
                SELECT id, ledger_id, file_path, note_id, title, category,
                       frontmatter_json, content_text, real_effect_time,
                       sys_write_time, effective_until, superseded_by, recorded_at
                FROM memory_history
                WHERE {' OR '.join(conditions)}
                ORDER BY id DESC
            """
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            
            history = []
            for r in rows:
                fm = {}
                if r['frontmatter_json']:
                    try:
                        fm = json.loads(r['frontmatter_json'])
                    except Exception:
                        fm = {}
                history.append({
                    "id": r['id'],
                    "ledger_id": r['ledger_id'],
                    "file_path": r['file_path'],
                    "note_id": r['note_id'],
                    "title": r['title'],
                    "category": r['category'],
                    "frontmatter": fm,
                    "content_text": r['content_text'],
                    "real_effect_time": r['real_effect_time'],
                    "sys_write_time": r['sys_write_time'],
                    "effective_until": r['effective_until'],
                    "superseded_by": r['superseded_by'],
                    "recorded_at": r['recorded_at']
                })
            return history

    def should_run_task(self, task_name: str, interval_days: int = 1) -> bool:
        """
        Check if a periodic task is due to run based on interval_days.
        interval_days=1 means once per calendar day.
        """
        today = datetime.date.today().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_run_date FROM task_execution_ledger WHERE task_name = ?", (task_name,))
            row = cursor.fetchone()
            if not row:
                return True
            if interval_days <= 0:
                return True
            last_date_str = row['last_run_date']
            if interval_days == 1:
                return last_date_str != today
            else:
                try:
                    last_dt = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
                    diff = (datetime.date.today() - last_dt).days
                    return diff >= interval_days
                except Exception:
                    return True

    def record_task_run(self, task_name: str, status: str = "success"):
        """Record that a task completed today."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO task_execution_ledger (task_name, last_run_date, last_run_time, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_name) DO UPDATE SET
                    last_run_date = excluded.last_run_date,
                    last_run_time = excluded.last_run_time,
                    status = excluded.status
            """, (task_name, today, now_time, status))
            conn.commit()


