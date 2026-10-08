import os
import time
import shutil
import tempfile
import pytest
from fastapi.testclient import TestClient

from src.aura_memory.schema import MemoryRecord, QueryRequest
from src.aura_memory.parser import parse_markdown_file, infer_category, parse_date_string
from src.aura_memory.db import AuraMemoryDB
from src.aura_memory.watcher import AuraMemoryEventHandler
from src.aura_memory.engine import AuraMemoryEngine
from src.aura_memory.api import app

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="aura_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def temp_db(temp_dir):
    db_path = os.path.join(temp_dir, "test_aura.db")
    return AuraMemoryDB(db_path=db_path)

# ----------------- 1. Parser Tests -----------------

def test_parser_with_frontmatter(temp_dir):
    file_path = os.path.join(temp_dir, "test_card.md")
    content = """---
id: test-001
title: 测试认知卡片
category: skills
date_created: 2025-06-01
sm2_ease: 2.8
sm2_interval: 3
sm2_next_review: 2025-06-04
tags:
  - 认知科学
  - 系统思维
---
这是正文内容。包含更多细节。
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    record = parse_markdown_file(file_path)
    assert record is not None
    assert record.note_id == "test-001"
    assert record.title == "测试认知卡片"
    assert record.real_effect_time == "2025-06-01"
    assert record.sm2_ease == 2.8
    assert record.sm2_interval == 3
    assert record.sm2_next_review == "2025-06-04"
    assert "认知科学" in record.tags
    assert "系统思维" in record.tags
    assert "这是正文内容" in record.content_text

def test_parser_without_frontmatter_fallback_date(temp_dir):
    file_path = os.path.join(temp_dir, "05 技能库", "决策心理学.md")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    content = """# 决策心理学
创建时间: 2024-11-15
这是一篇普通的笔记，带有内嵌标签 #心智模型。
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    record = parse_markdown_file(file_path)
    assert record is not None
    assert record.title == "决策心理学"
    assert record.category == "skills"
    assert record.real_effect_time == "2024-11-15"
    assert "心智模型" in record.tags
    assert record.sm2_ease == 2.5
    assert record.sm2_next_review == "2024-11-16"  # 1 day after creation date

# ----------------- 2. DB & Bi-Temporal Tests -----------------

def test_db_upsert_and_fts_query(temp_db):
    rec = MemoryRecord(
        note_id="rec-1",
        file_path="/mock/vault/skills/资产配置策略.md",
        title="资产配置策略",
        category="skills",
        frontmatter={"risk": "medium"},
        content_text="本文详细阐述桥水全天候策略的底层逻辑与风险平价算法。",
        real_effect_time="2025-01-10",
        sys_write_time="2025-01-10 10:00:00",
        tags=["投资", "全天候"]
    )
    temp_db.upsert_record(rec)

    # 1. FTS search
    res = temp_db.query_temporal(QueryRequest(query="风险平价", as_of="2025-02-01"))
    assert res.count == 1
    assert res.results[0].title == "资产配置策略"
    assert "全天候" in res.results[0].tags

    # 2. Update record
    rec_v2 = rec.model_copy(update={"content_text": "桥水全天候策略升级版，加入宏观对冲。"})
    temp_db.upsert_record(rec_v2)
    res_v2 = temp_db.query_temporal(QueryRequest(query="宏观对冲", as_of="2025-02-01"))
    assert res_v2.count == 1
    assert "升级版" in res_v2.results[0].snippet

def test_db_bi_temporal_filtering(temp_db):
    # Old decision (made 2024-01-01, superseded on 2025-01-01 by new decision)
    old_decision = MemoryRecord(
        note_id="decision-2024",
        file_path="/mock/vault/decisions/配置决策2024.md",
        title="2024年资产配置决议",
        category="projects",
        content_text="重仓美股ETF与短债。",
        real_effect_time="2024-01-01",
        sys_write_time="2024-01-01 10:00:00",
        effective_until="2025-01-01",
        superseded_by="decision-2025",
        tags=["决策"]
    )
    # New decision (effective 2025-01-01)
    new_decision = MemoryRecord(
        note_id="decision-2025",
        file_path="/mock/vault/decisions/配置决策2025.md",
        title="2025年资产配置决议",
        category="projects",
        content_text="转向大宗商品与抗通胀国债。",
        real_effect_time="2025-01-01",
        sys_write_time="2025-01-01 10:00:00",
        effective_until=None,
        superseded_by=None,
        tags=["决策"]
    )
    temp_db.upsert_record(old_decision)
    temp_db.upsert_record(new_decision)

    # Query as of 2024-06-01 (Time travel to mid-2024)
    res_mid_2024 = temp_db.query_temporal(QueryRequest(query="配置决议", as_of="2024-06-01"))
    assert res_mid_2024.count == 1
    assert res_mid_2024.results[0].note_id == "decision-2024"

    # Query as of 2025-06-01 (In 2025, old decision is superseded and excluded)
    res_2025 = temp_db.query_temporal(QueryRequest(query="配置决议", as_of="2025-06-01"))
    assert res_2025.count == 1
    assert res_2025.results[0].note_id == "decision-2025"

    # Query with include_superseded=True
    res_all = temp_db.query_temporal(QueryRequest(query="配置决议", as_of="2025-06-01", include_superseded=True))
    assert res_all.count == 2

def test_db_sm2_due_cards(temp_db):
    card1 = MemoryRecord(
        note_id="c1",
        file_path="/mock/card1.md",
        title="卡片1",
        category="skills",
        real_effect_time="2026-01-01",
        sys_write_time="2026-01-01 10:00:00",
        sm2_next_review="2026-03-01"
    )
    card2 = MemoryRecord(
        note_id="c2",
        file_path="/mock/card2.md",
        title="卡片2",
        category="skills",
        real_effect_time="2026-01-01",
        sys_write_time="2026-01-01 10:00:00",
        sm2_next_review="2026-03-10"
    )
    temp_db.upsert_record(card1)
    temp_db.upsert_record(card2)

    # Check due on 2026-03-05 -> only card1 is due
    due = temp_db.get_due_reviews("2026-03-05")
    assert len(due) == 1
    assert due[0].title == "卡片1"

    # Check due on 2026-03-15 -> both cards due
    due_all = temp_db.get_due_reviews("2026-03-15")
    assert len(due_all) == 2

# ----------------- 3. Watchdog Handler Tests -----------------

def test_watcher_event_handler_debounce(temp_db, temp_dir):
    handler = AuraMemoryEventHandler(db=temp_db, debounce_seconds=0.2)
    
    file_path = os.path.join(temp_dir, "debounce_test.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# Debounce Initial")

    # Simulate multiple rapid modifications
    class FakeEvent:
        def __init__(self, path):
            self.src_path = path
            self.is_directory = False

    handler.on_modified(FakeEvent(file_path))
    handler.on_modified(FakeEvent(file_path))
    handler.on_modified(FakeEvent(file_path))
    
    # Wait for debounce to expire
    time.sleep(0.35)

    stats = temp_db.get_stats()
    assert stats["total_records"] == 1

# ----------------- 4. FastAPI API Tests -----------------

def test_api_endpoints(temp_db, monkeypatch):
    # Mock engine's DB with temp_db
    class MockEngine:
        def __init__(self, db):
            self.db = db
            self.watch_dirs = ["/mock/dir"]
            self.watcher = type("Watcher", (), {"_is_running": True})()
            self.inbox_worker = type("InboxWorker", (), {
                "_is_running": True,
                "get_status": lambda self=None: {"is_running": True, "queue_size": 0, "processed_count": 0}
            })()
        def query(self, r): return self.db.query_temporal(r)

        def get_profile(self): return self.db.get_profile_view()
        def get_due_reviews(self, d=None, categories=None): return self.db.get_due_reviews(d, categories=categories)
        def get_stats(self): return self.db.get_stats()
        def sync_all(self): return {"synced": 1}

    mock_engine = MockEngine(temp_db)
    monkeypatch.setattr("src.aura_memory.api.get_engine", lambda: mock_engine)

    client = TestClient(app)

    # 1. Health check
    res_health = client.get("/memory/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    # 2. Stats
    res_stats = client.get("/memory/stats")
    assert res_stats.status_code == 200

    # 3. Query
    res_query = client.post("/memory/query", json={"query": "test"})
    assert res_query.status_code == 200
    assert "results" in res_query.json()

    # 4. Reviews due
    res_due = client.get("/memory/reviews/due?target_date=2026-03-01")
    assert res_due.status_code == 200
    assert "due_cards" in res_due.json()

    # 5. Profile
    res_profile = client.get("/memory/profile")
    assert res_profile.status_code == 200
    assert "active_projects" in res_profile.json()

# ----------------- 5. Phase 2: Bi-Temporal History & InboxWorker Tests -----------------

def test_db_audit_history(temp_db):
    # Initial note
    rec_v1 = MemoryRecord(
        note_id="strat-01",
        file_path="/mock/vault/skills/商业模式分析.md",
        title="商业模式分析",
        category="skills",
        frontmatter={"stage": "seed"},
        content_text="版本 1：关注用户规模与病毒式裂变增长。",
        real_effect_time="2025-01-01",
        sys_write_time="2025-01-01 12:00:00",
        tags=["商业", "增长"]
    )
    temp_db.upsert_record(rec_v1)
    
    # Check history initially empty
    hist0 = temp_db.get_card_history(note_id="strat-01")
    assert len(hist0) == 0

    # Note updated with new insight
    rec_v2 = rec_v1.model_copy(update={
        "content_text": "版本 2：转向健康的正向单位经济模型 (Unit Economics)。",
        "real_effect_time": "2025-06-01",
        "sys_write_time": "2025-06-01 14:00:00"
    })
    temp_db.upsert_record(rec_v2)

    # Check history contains v1
    hist1 = temp_db.get_card_history(note_id="strat-01")
    assert len(hist1) == 1
    assert hist1[0]["note_id"] == "strat-01"
    assert "病毒式裂变" in hist1[0]["content_text"]
    assert hist1[0]["effective_until"] == "2025-06-01"
    assert hist1[0]["superseded_by"] == "strat-01"

    # Note updated again
    rec_v3 = rec_v2.model_copy(update={
        "content_text": "版本 3：建立网络效应与生态护城河。",
        "real_effect_time": "2026-01-01",
        "sys_write_time": "2026-01-01 09:00:00"
    })
    temp_db.upsert_record(rec_v3)

    hist2 = temp_db.get_card_history(file_path="/mock/vault/skills/商业模式分析.md")
    assert len(hist2) == 2
    assert "单位经济模型" in hist2[0]["content_text"]
    assert "病毒式裂变" in hist2[1]["content_text"]

def test_inbox_worker_queue_and_ignore_lock(temp_dir):
    from src.aura_memory.inbox_worker import InboxWorker
    from src.aura_memory.watcher import AuraMemoryEventHandler
    from src.scheduler import mark_task_completed
    
    # Setup dummy watcher handler for ignore_path
    class DummyWatcherHandler:
        def __init__(self):
            self.ignored = []
        from contextlib import contextmanager
        @contextmanager
        def ignore_path(self, path):
            self.ignored.append(path)
            yield

    dummy_handler = DummyWatcherHandler()
    processed_tasks = []

    def mock_processor(task):
        processed_tasks.append(task)
        mark_task_completed(task['file_path'], task['original_line'])
        return True

    worker = InboxWorker(watcher_handler=dummy_handler, task_processor=mock_processor)
    worker.start()

    inbox_file = os.path.join(temp_dir, "Inbox.md")
    with open(inbox_file, "w", encoding="utf-8") as f:
        f.write("## 任务\n- [ ] #待处理 2026-09-09 21:00 | https://v.douyin.com/test123/\n")

    worker.enqueue(inbox_file)

    # Wait briefly for worker to complete
    worker.queue.join()
    worker.stop()

    assert len(processed_tasks) == 1
    assert "https://v.douyin.com/test123/" in processed_tasks[0]['payload']
    assert len(dummy_handler.ignored) == 1
    assert os.path.normpath(dummy_handler.ignored[0]) == os.path.normpath(inbox_file)

    # Verify file was marked completed
    with open(inbox_file, "r", encoding="utf-8") as f:
        new_content = f.read()
    assert "- [x] #已处理" in new_content

def test_api_history_and_inbox_status(temp_db, monkeypatch):
    class MockEngine:
        def __init__(self, db):
            self.db = db
            self.watch_dirs = ["/mock/dir"]
            self.watcher = type("Watcher", (), {"_is_running": True})()
            self.inbox_worker = type("InboxWorker", (), {
                "_is_running": True,
                "get_status": lambda self=None: {"is_running": True, "queue_size": 0, "processed_count": 5}
            })()

        def get_history(self, file_path=None, note_id=None):
            return self.db.get_card_history(file_path=file_path, note_id=note_id)
        def get_inbox_status(self):
            return self.inbox_worker.get_status()

    # Pre-populate history
    rec1 = MemoryRecord(
        note_id="hist-test",
        file_path="/mock/test_hist.md",
        title="历史测试",
        category="skills",
        content_text="初版内容",
        real_effect_time="2025-01-01",
        sys_write_time="2025-01-01 10:00:00"
    )
    temp_db.upsert_record(rec1)
    rec2 = rec1.model_copy(update={"content_text": "第二版内容"})
    temp_db.upsert_record(rec2)

    mock_engine = MockEngine(temp_db)
    monkeypatch.setattr("src.aura_memory.api.get_engine", lambda: mock_engine)

    client = TestClient(app)

    # 1. Test history endpoint
    res_hist = client.get("/memory/history?note_id=hist-test")
    assert res_hist.status_code == 200
    data = res_hist.json()
    assert data["count"] == 1
    assert "初版内容" in data["history"][0]["content_text"]

    # 2. Test inbox status endpoint
    res_inbox = client.get("/memory/inbox/status")
    assert res_inbox.status_code == 200
    assert res_inbox.json()["processed_count"] == 5

def test_spaced_review_fast_integration(temp_db, temp_dir, monkeypatch):
    from src.spaced_review import process_spaced_review_fast
    import datetime

    # Monkeypatch REVIEW_DIR to temp_dir to avoid modifying real vault
    test_review_dir = os.path.join(temp_dir, "03 资产库_Areas", "每日复习")
    monkeypatch.setattr("src.spaced_review.REVIEW_DIR", test_review_dir)
    monkeypatch.setattr("src.spaced_review.enhance_due_cards", lambda due, all_f: None)
    # Monkeypatch notification to avoid desktop popup during tests
    monkeypatch.setattr("src.spaced_review.notification.notify", lambda **kwargs: None)

    # Insert a card due today
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    due_rec = MemoryRecord(
        note_id="due-skill-01",
        file_path=os.path.join(temp_dir, "技能卡片.md"),
        title="技能卡片",
        category="skills",
        real_effect_time="2025-01-01",
        sys_write_time="2025-01-01 10:00:00",
        sm2_ease=2.5,
        sm2_interval=1,
        sm2_next_review=today_str
    )
    temp_db.upsert_record(due_rec)

    class DummyEngine:
        def __init__(self, db):
            self.db = db
        def get_due_reviews(self, d=None, categories=None):
            return self.db.get_due_reviews(d, categories=categories)

    engine = DummyEngine(temp_db)
    result_path = process_spaced_review_fast(engine)

    assert result_path is not None
    assert os.path.exists(result_path)
    with open(result_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "[[技能卡片]]" in content
    assert "今日待复习" in content

def test_laap_agent_perceive_integration(temp_db, monkeypatch):
    from src.laap_agent.engine import perceive_environment

    # Insert active projects and insights into DB
    p1 = MemoryRecord(
        note_id="proj-1",
        file_path="/mock/p1.md",
        title="Obsidian生态引擎",
        category="projects",
        real_effect_time="2026-03-01",
        sys_write_time="2026-03-01 10:00:00"
    )
    i1 = MemoryRecord(
        note_id="ins-1",
        file_path="/mock/i1.md",
        title="反事实推演洞见",
        category="insights",
        real_effect_time="2026-03-05",
        sys_write_time="2026-03-05 10:00:00"
    )
    temp_db.upsert_record(p1)
    temp_db.upsert_record(i1)

    class DummyEngine:
        def __init__(self, db):
            self.db = db
        def get_profile(self):
            return self.db.get_profile_view()

    dummy_engine = DummyEngine(temp_db)
    try:
        import aura_memory.engine
        monkeypatch.setattr(aura_memory.engine, "get_engine", lambda: dummy_engine)
    except ImportError:
        pass
    try:
        import src.aura_memory.engine
        monkeypatch.setattr(src.aura_memory.engine, "get_engine", lambda: dummy_engine)
    except ImportError:
        pass

    ctx = perceive_environment()

    assert "Obsidian生态引擎" in ctx.active_projects
    assert "反事实推演洞见" in ctx.recent_insights
    assert ctx.review_stats["total_records"] == 2


def test_task_execution_ledger(temp_db):
    # 1. Unrun task should return True
    assert temp_db.should_run_task("daily_digest", interval_days=1) is True

    # 2. Record run
    temp_db.record_task_run("daily_digest", status="success")

    # 3. Should not run again on same day (interval_days=1)
    assert temp_db.should_run_task("daily_digest", interval_days=1) is False

    # 4. Another task should still run
    assert temp_db.should_run_task("spaced_review", interval_days=1) is True

    # 5. Non-existent or past day simulation: if interval_days=0, it should run
    assert temp_db.should_run_task("daily_digest", interval_days=0) is True

