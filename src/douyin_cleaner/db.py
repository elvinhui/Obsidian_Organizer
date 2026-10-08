import sqlite3
import datetime
import os
from typing import Optional, List, Dict, Any

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit.db")

def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH):
    """Initializes the database schema if it doesn't already exist."""
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS followings (
                sec_uid TEXT PRIMARY KEY,
                uid TEXT,
                short_id TEXT,
                nickname TEXT NOT NULL,
                avatar TEXT,
                signature TEXT,
                follower_status INTEGER DEFAULT 0,
                following_date TEXT,
                last_publish_time TEXT,
                days_inactive INTEGER DEFAULT 0,
                is_canceled INTEGER DEFAULT 0,
                is_private INTEGER DEFAULT 0,
                audit_status TEXT DEFAULT 'pending',
                audit_note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_status ON followings(audit_status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_canceled ON followings(is_canceled);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_days_inactive ON followings(days_inactive);")
        conn.commit()

def upsert_following(db_path: str, data: Dict[str, Any]) -> bool:
    """Inserts or updates a following user's basic info without overwriting existing audit state."""
    sec_uid = data.get("sec_uid")
    if not sec_uid:
        return False
        
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO followings (
                sec_uid, uid, short_id, nickname, avatar, signature, follower_status, following_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sec_uid) DO UPDATE SET
                uid = coalesce(excluded.uid, followings.uid),
                short_id = coalesce(excluded.short_id, followings.short_id),
                nickname = excluded.nickname,
                avatar = coalesce(excluded.avatar, followings.avatar),
                signature = coalesce(excluded.signature, followings.signature),
                follower_status = coalesce(excluded.follower_status, followings.follower_status),
                updated_at = excluded.updated_at
        """, (
            sec_uid,
            data.get("uid"),
            data.get("short_id"),
            data.get("nickname", "未知用户"),
            data.get("avatar"),
            data.get("signature"),
            data.get("follower_status", 0),
            data.get("following_date"),
            now
        ))
        conn.commit()
    return True

def batch_upsert_followings(db_path: str, items: List[Dict[str, Any]]) -> int:
    """Batch inserts or updates a list of following users."""
    count = 0
    for item in items:
        if upsert_following(db_path, item):
            count += 1
    return count

def update_audit_result(
    db_path: str,
    sec_uid: str,
    is_canceled: bool = False,
    last_publish_time: Optional[str] = None,
    days_inactive: int = 0,
    is_private: bool = False,
    audit_note: str = ""
) -> bool:
    """Updates the audit outcome for a specific user."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE followings SET
                is_canceled = ?,
                last_publish_time = ?,
                days_inactive = ?,
                is_private = ?,
                audit_status = 'audited',
                audit_note = ?,
                updated_at = ?
            WHERE sec_uid = ?
        """, (
            1 if is_canceled else 0,
            last_publish_time,
            days_inactive,
            1 if is_private else 0,
            audit_note,
            now,
            sec_uid
        ))
        conn.commit()
        return cursor.rowcount > 0

def update_following_status(
    db_path: str,
    sec_uid: str,
    status: str,
    audit_note: Optional[str] = None
) -> bool:
    """Updates following status (e.g. pending_delete, deleted, kept, error)."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if audit_note is not None:
            cursor.execute("""
                UPDATE followings SET
                    audit_status = ?,
                    audit_note = ?,
                    updated_at = ?
                WHERE sec_uid = ?
            """, (status, audit_note, now, sec_uid))
        else:
            cursor.execute("""
                UPDATE followings SET
                    audit_status = ?,
                    updated_at = ?
                WHERE sec_uid = ?
            """, (status, now, sec_uid))
        conn.commit()
        return cursor.rowcount > 0

def get_followings(
    db_path: str = DEFAULT_DB_PATH,
    sec_uid: Optional[str] = None,
    audit_status: Optional[str] = None,
    is_canceled: Optional[bool] = None,
    min_inactive_days: Optional[int] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Queries followings with optional filters."""
    query = "SELECT * FROM followings WHERE 1=1"
    params = []
    
    if sec_uid:
        query += " AND sec_uid = ?"
        params.append(sec_uid)
    if audit_status:
        query += " AND audit_status = ?"
        params.append(audit_status)
    if is_canceled is not None:
        query += " AND is_canceled = ?"
        params.append(1 if is_canceled else 0)
    if min_inactive_days is not None:
        query += " AND days_inactive >= ?"
        params.append(min_inactive_days)
        
    query += " ORDER BY is_canceled DESC, days_inactive DESC, updated_at DESC"
    
    if limit is not None:
        query += f" LIMIT {int(limit)}"
        
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return cursor.fetchall()

def get_audit_stats(db_path: str = DEFAULT_DB_PATH) -> Dict[str, int]:
    """Computes summary statistics for followings."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM followings;")
        total = cursor.fetchone()["cnt"]
        
        cursor.execute("SELECT COUNT(*) as cnt FROM followings WHERE audit_status = 'pending';")
        pending = cursor.fetchone()["cnt"]
        
        cursor.execute("SELECT COUNT(*) as cnt FROM followings WHERE audit_status = 'audited';")
        audited = cursor.fetchone()["cnt"]
        
        cursor.execute("SELECT COUNT(*) as cnt FROM followings WHERE is_canceled = 1;")
        canceled = cursor.fetchone()["cnt"]
        
        cursor.execute("SELECT COUNT(*) as cnt FROM followings WHERE days_inactive >= 180 AND is_canceled = 0;")
        inactive_180 = cursor.fetchone()["cnt"]
        
        cursor.execute("SELECT COUNT(*) as cnt FROM followings WHERE days_inactive >= 360 AND is_canceled = 0;")
        inactive_360 = cursor.fetchone()["cnt"]
        
        cursor.execute("SELECT COUNT(*) as cnt FROM followings WHERE audit_status = 'deleted';")
        deleted = cursor.fetchone()["cnt"]
        
        return {
            "total": total,
            "pending": pending,
            "audited": audited,
            "canceled": canceled,
            "inactive_180": inactive_180,
            "inactive_360": inactive_360,
            "deleted": deleted
        }
