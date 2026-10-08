import pytest
import sqlite3
import os
from src.douyin_cleaner.db import (
    init_db,
    upsert_following,
    batch_upsert_followings,
    get_followings,
    update_audit_result,
    update_following_status,
    get_audit_stats,
)

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_audit.db")
    init_db(db_file)
    return db_file

def test_init_db(test_db):
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='followings';")
    assert cursor.fetchone() is not None
    conn.close()

def test_upsert_and_get_following(test_db):
    item = {
        "sec_uid": "SEC_UID_1",
        "uid": "123456",
        "nickname": "TestUser1",
        "avatar": "https://p3.douyinpic.com/test.jpg",
        "signature": "Hello world"
    }
    upsert_following(test_db, item)
    
    results = get_followings(test_db)
    assert len(results) == 1
    assert results[0]["sec_uid"] == "SEC_UID_1"
    assert results[0]["nickname"] == "TestUser1"
    assert results[0]["audit_status"] == "pending"

def test_batch_upsert_followings(test_db):
    items = [
        {"sec_uid": f"SEC_{i}", "uid": f"UID_{i}", "nickname": f"User_{i}"}
        for i in range(5)
    ]
    count = batch_upsert_followings(test_db, items)
    assert count == 5
    
    results = get_followings(test_db)
    assert len(results) == 5

def test_update_audit_result(test_db):
    item = {"sec_uid": "SEC_ZOMBIE", "nickname": "ZombieUser"}
    upsert_following(test_db, item)
    
    # Mark as inactive 200 days
    update_audit_result(
        test_db,
        sec_uid="SEC_ZOMBIE",
        is_canceled=False,
        last_publish_time="2026-01-01",
        days_inactive=240,
        is_private=False,
        audit_note="超过180天未更新"
    )
    
    res = get_followings(test_db, sec_uid="SEC_ZOMBIE")
    assert len(res) == 1
    assert res[0]["days_inactive"] == 240
    assert res[0]["audit_status"] == "audited"
    assert res[0]["is_canceled"] == 0

def test_update_status_and_stats(test_db):
    items = [
        {"sec_uid": "S1", "nickname": "CanceledUser"},
        {"sec_uid": "S2", "nickname": "ZombieUser"},
        {"sec_uid": "S3", "nickname": "ActiveUser"},
    ]
    batch_upsert_followings(test_db, items)
    
    update_audit_result(test_db, "S1", is_canceled=True, days_inactive=999, audit_note="账号注销")
    update_audit_result(test_db, "S2", is_canceled=False, days_inactive=200, audit_note="长期未更新")
    update_audit_result(test_db, "S3", is_canceled=False, days_inactive=5, audit_note="活跃")
    
    stats = get_audit_stats(test_db)
    assert stats["total"] == 3
    assert stats["canceled"] == 1
    assert stats["inactive_180"] == 1
    
    # Mark S1 as deleted
    update_following_status(test_db, "S1", "deleted", "取关成功")
    stats_after = get_audit_stats(test_db)
    assert stats_after["deleted"] == 1
