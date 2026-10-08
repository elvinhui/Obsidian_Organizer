import os
import datetime
import pytest
from src.spaced_review import (
    MAX_DAILY_REVIEWS,
    calculate_card_priority,
    stagger_and_cap_due_cards,
    process_checklist_completions
)
from src.aura_memory.schema import MemoryRecord

def test_calculate_card_priority():
    # If-Then/Action card should have higher priority
    action_p = calculate_card_priority("反拖延：物理熔断SOP", "", 1)
    concept_p = calculate_card_priority("中世纪历史概述", "", 30)
    assert action_p > concept_p
    assert action_p >= 50.0

def test_stagger_and_cap_due_cards(temp_db, temp_dir):
    today = datetime.date(2026, 9, 10)
    
    # Create 20 mock due cards
    mock_cards = []
    for i in range(20):
        fpath = os.path.join(temp_dir, f"card_{i}.md")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(f"---\nsm2_next_review: '2026-09-01'\nsm2_ease: 2.5\nsm2_interval: 1\n---\n# Card {i}\n")
        
        rec = MemoryRecord(
            note_id=f"card-{i}",
            file_path=fpath,
            title=f"Card {i}" if i != 0 else "反拖延战备触发器",
            category="skills",
            real_effect_time="2026-09-01",
            sys_write_time="2026-09-01 10:00:00",
            sm2_ease=2.5,
            sm2_interval=1,
            sm2_next_review="2026-09-01"
        )
        temp_db.upsert_record(rec)
        
        mock_cards.append({
            "title": rec.title,
            "interval": 1,
            "ease": 2.5,
            "filepath": fpath
        })
        
    class MockEngine:
        def __init__(self, db):
            self.db = db
            self.watcher = None
            
    engine = MockEngine(temp_db)
    
    # Execute cap & stagger
    today_cards = stagger_and_cap_due_cards(mock_cards, today, engine=engine, max_daily=7)
    
    # 1. Today must be strictly capped at 7
    assert len(today_cards) == 7
    # 2. Priority card must be in today's 7
    titles = [c['title'] for c in today_cards]
    assert "反拖延战备触发器" in titles
    
    # 3. Check SQLite updates for overflow cards
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memory_ledger WHERE sm2_next_review > '2026-09-10'")
        staggered_count = cursor.fetchone()[0]
        # 20 - 7 = 13 overflow cards should have future dates
        assert staggered_count == 13

def test_process_checklist_completions(temp_db, temp_dir):
    today = datetime.date(2026, 9, 10)
    card_path = os.path.join(temp_dir, "执行控制二分法.md")
    with open(card_path, "w", encoding="utf-8") as f:
        f.write("---\nsm2_next_review: '2026-09-10'\nsm2_ease: 2.5\nsm2_interval: 1\n---\n# 执行控制二分法\n")
        
    rec = MemoryRecord(
        note_id="card-ctrl",
        file_path=card_path,
        title="执行控制二分法",
        category="skills",
        real_effect_time="2026-09-10",
        sys_write_time="2026-09-10 10:00:00",
        sm2_ease=2.5,
        sm2_interval=1,
        sm2_next_review="2026-09-10"
    )
    temp_db.upsert_record(rec)
    
    checklist_path = os.path.join(temp_dir, "间隔复习_2026-09-10.md")
    with open(checklist_path, "w", encoding="utf-8") as f:
        f.write("# 间隔复习\n- [x] [[执行控制二分法]] (当前间隔: 1天)\n- [ ] [[未读卡片]]\n")
        
    class MockEngine:
        def __init__(self, db):
            self.db = db
            self.watcher = None
            
    engine = MockEngine(temp_db)
    completed = process_checklist_completions(checklist_path, today, engine=engine)
    
    assert completed == 1
    # Check that checklist was updated with #已完成
    with open(checklist_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "- [x] [[执行控制二分法]] (当前间隔: 1天) #已完成" in content
    assert "- [ ] [[未读卡片]]" in content
    
    # Check that DB was updated with new doubled interval (1 -> 2 days)
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sm2_interval, sm2_next_review FROM memory_ledger WHERE title = '执行控制二分法'")
        row = cursor.fetchone()
        assert row['sm2_interval'] == 2
        assert row['sm2_next_review'] == "2026-09-12"

    # Check card frontmatter was updated and sm2_score cleared
    with open(card_path, "r", encoding="utf-8") as f:
        card_content = f.read()
    assert "sm2_next_review: '2026-09-12'" in card_content or 'sm2_next_review: "2026-09-12"' in card_content or "sm2_next_review: 2026-09-12" in card_content
    assert "sm2_interval: 2" in card_content

    # Second run should skip already completed items
    second_run = process_checklist_completions(checklist_path, today, engine=engine)
    assert second_run == 0

def test_watcher_review_checklist_debounce(temp_db, temp_dir):
    import time
    from src.aura_memory.watcher import AuraMemoryEventHandler
    
    card_path = os.path.join(temp_dir, "专注熔断法.md")
    with open(card_path, "w", encoding="utf-8") as f:
        f.write("---\nsm2_next_review: '2026-09-10'\nsm2_ease: 2.5\nsm2_interval: 2\n---\n# 专注熔断法\n")
        
    rec = MemoryRecord(
        note_id="card-focus",
        file_path=card_path,
        title="专注熔断法",
        category="skills",
        real_effect_time="2026-09-10",
        sys_write_time="2026-09-10 10:00:00",
        sm2_ease=2.5,
        sm2_interval=2,
        sm2_next_review="2026-09-10"
    )
    temp_db.upsert_record(rec)
    
    checklist_path = os.path.join(temp_dir, "间隔复习_2026-09-10.md")
    with open(checklist_path, "w", encoding="utf-8") as f:
        f.write("# 间隔复习\n- [x] [[专注熔断法]] (当前间隔: 2天)\n")
        
    handler = AuraMemoryEventHandler(db=temp_db, debounce_seconds=0.1)
    
    class FakeEvent:
        def __init__(self, path):
            self.src_path = path
            self.is_directory = False
            
    handler.on_modified(FakeEvent(checklist_path))
    time.sleep(0.3)
    
    # Verify checklist updated with #已完成
    with open(checklist_path, "r", encoding="utf-8") as f:
        chk_content = f.read()
    assert "- [x] [[专注熔断法]] (当前间隔: 2天) #已完成" in chk_content
    
    # Verify DB interval doubled from 2 to 4
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sm2_interval, sm2_next_review FROM memory_ledger WHERE title = '专注熔断法'")
        row = cursor.fetchone()
        assert row['sm2_interval'] == 4
        
    # Verify card frontmatter interval updated to 4
    with open(card_path, "r", encoding="utf-8") as f:
        card_content = f.read()
    assert "sm2_interval: 4" in card_content
