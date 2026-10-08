"""
Obsidian SM-2 Spaced Repetition Python CLI
Scans the skill library, processes SM-2 memory feedback from YAML frontmatter,
and generates a dynamic daily review checklist.
Sends a desktop toast notification if cards are due.
"""

import os
import re
import logging
import datetime
from plyer import notification
import frontmatter
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import SKILLS_DIR, INSIGHTS_DIR, OBSIDIAN_BASE_PATH

from auto_linker import extract_card_info, cosine_similarity, generate_embeddings, client, SIMILARITY_THRESHOLD

import json
from google.genai import types

logger = logging.getLogger(__name__)

REVIEW_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每日复习")
MAX_DAILY_REVIEWS = 7

def calculate_card_priority(title: str, filepath: str, interval: int) -> float:
    """
    Score cards to pick the most actionable and time-sensitive for today.
    Higher score = higher priority for today's review.
    """
    score = 0.0
    action_keywords = ["if-then", "触发器", "战备", "sop", "清单", "行动", "反拖延", "决策", "熔断", "复利", "模型"]
    t_lower = title.lower()
    if any(k in t_lower for k in action_keywords):
        score += 50.0
        
    try:
        if filepath and os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                head = f.read(600).lower()
                if "if-then" in head or "触发器" in head or "战备" in head:
                    score += 30.0
    except Exception:
        pass
        
    # Ebbinghaus: smaller interval needs reinforcement sooner (interval 0,1 gets highest boost)
    score += max(0.0, 20.0 - float(interval or 0))
    return score

def _update_card_frontmatter_meta(filepath: str, new_date_str: str, new_interval: int | None = None):
    """Update sm2_next_review and sm2_interval in markdown frontmatter safely, clearing manual sm2_score."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
        post.metadata['sm2_next_review'] = new_date_str
        if new_interval is not None:
            post.metadata['sm2_interval'] = new_interval
        # Clear legacy sm2_score so user never feels obligated to fill it
        post.metadata['sm2_score'] = None
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        logger.debug(f"Failed to update frontmatter for {filepath}: {e}")

def _update_card_frontmatter_date(filepath: str, new_date_str: str):
    """Compatibility wrapper for updating date."""
    _update_card_frontmatter_meta(filepath, new_date_str)

def stagger_and_cap_due_cards(due_cards: list, today: datetime.date, engine=None, max_daily: int = MAX_DAILY_REVIEWS) -> list:
    """
    Intelligent Anti-Snowball Cap:
    1. If len(due_cards) <= max_daily, return due_cards.
    2. Prioritize actionable cards & recent cards.
    3. Retain the top `max_daily` cards for today's review checklist.
    4. Auto-stagger overflow overdue cards evenly across future days (e.g. next 1..N days).
    5. Sync new dates to SQLite ledger and file frontmatters.
    """
    if len(due_cards) <= max_daily:
        return due_cards

    logger.info(f"🛡️ Anti-Snowball Cap triggered: {len(due_cards)} overdue cards detected (cap={max_daily}).")

    scored = []
    for card in due_cards:
        p = calculate_card_priority(card.get('title', ''), card.get('filepath', ''), card.get('interval', 0))
        scored.append((p, card))
        
    scored.sort(key=lambda x: (-x[0], x[1].get('interval', 0)))

    today_cards = [item[1] for item in scored[:max_daily]]
    overflow_cards = [item[1] for item in scored[max_daily:]]

    updates = []
    for idx, card in enumerate(overflow_cards):
        day_offset = (idx // max_daily) + 1
        new_date = today + datetime.timedelta(days=day_offset)
        new_date_str = new_date.strftime("%Y-%m-%d")
        updates.append((card, new_date_str))

    if engine and hasattr(engine, 'db') and engine.db:
        with engine.db.get_connection() as conn:
            cursor = conn.cursor()
            for card, new_date_str in updates:
                cursor.execute(
                    "UPDATE memory_ledger SET sm2_next_review = ? WHERE file_path = ?",
                    (new_date_str, card['filepath'])
                )
            conn.commit()

    watcher_handler = None
    if engine and hasattr(engine, 'watcher') and engine.watcher and hasattr(engine.watcher, 'handler'):
        watcher_handler = engine.watcher.handler

    for card, new_date_str in updates:
        fpath = card.get('filepath')
        if not fpath or not os.path.exists(fpath):
            continue
        if watcher_handler and hasattr(watcher_handler, 'ignore_path'):
            with watcher_handler.ignore_path(fpath):
                _update_card_frontmatter_date(fpath, new_date_str)
        else:
            _update_card_frontmatter_date(fpath, new_date_str)

    days_spread = (len(overflow_cards) // max_daily) + 1
    logger.info(f"✅ Successfully staggered {len(overflow_cards)} overdue cards across the next {days_spread} days. Today capped at {len(today_cards)} cards.")
    return today_cards

def process_checklist_completions(review_file_path: str, today: datetime.date = None, engine=None, db=None, watcher_handler=None) -> int:
    """
    Parse checked boxes `- [x] [[Card Title]]` in the review checklist file.
    Automatically advances the review interval (x2) into the future
    without requiring manual YAML editing.
    """
    if not os.path.exists(review_file_path):
        return 0
        
    if today is None:
        today = datetime.date.today()
        
    try:
        with open(review_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Failed to read checklist {review_file_path}: {e}")
        return 0
        
    checked_pattern = re.compile(r'^\s*-\s*\[x\]\s*\[\[(.*?)\]\]')
    completed_count = 0
    new_lines = []
    
    target_db = None
    if engine and hasattr(engine, 'db') and engine.db:
        target_db = engine.db
    elif db:
        target_db = db

    if not watcher_handler and engine and hasattr(engine, 'watcher') and engine.watcher and hasattr(engine.watcher, 'handler'):
        watcher_handler = engine.watcher.handler
    
    for line in lines:
        if "#已完成" in line or "#已处理" in line:
            new_lines.append(line)
            continue
            
        match = checked_pattern.match(line)
        if match:
            card_title = match.group(1).strip()
            if target_db:
                with target_db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT file_path, sm2_ease, sm2_interval FROM memory_ledger WHERE title = ? OR file_path LIKE ?",
                        (card_title, f"%{card_title}.md")
                    )
                    row = cursor.fetchone()
                    if row:
                        fpath = row['file_path']
                        interval = int(row['sm2_interval'] or 0)
                        # Double the interval (minimum 2 days if previously 0 or 1)
                        if interval <= 0:
                            new_interval = 2
                        elif interval == 1:
                            new_interval = 2
                        else:
                            new_interval = interval * 2
                            
                        next_date = today + datetime.timedelta(days=new_interval)
                        next_date_str = next_date.strftime("%Y-%m-%d")
                        
                        cursor.execute(
                            "UPDATE memory_ledger SET sm2_interval = ?, sm2_next_review = ? WHERE file_path = ?",
                            (new_interval, next_date_str, fpath)
                        )
                        target_db.clear_sm2_score(fpath) if hasattr(target_db, 'clear_sm2_score') else None
                        conn.commit()
                        
                        if watcher_handler and hasattr(watcher_handler, 'ignore_path'):
                            with watcher_handler.ignore_path(fpath):
                                _update_card_frontmatter_meta(fpath, next_date_str, new_interval)
                        else:
                            _update_card_frontmatter_meta(fpath, next_date_str, new_interval)
                            
                        completed_count += 1
                        logger.info(f"✅ Advanced SM-2 for checked card '{card_title}': interval {interval}d -> {new_interval}d, next review on {next_date_str}")
                        line = line.rstrip() + " #已完成\n"
        new_lines.append(line)
        
    if completed_count > 0:
        try:
            if watcher_handler and hasattr(watcher_handler, 'ignore_path'):
                with watcher_handler.ignore_path(review_file_path):
                    with open(review_file_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
            else:
                with open(review_file_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            logger.info(f"🎉 Automatically recorded {completed_count} checked review cards!")
        except Exception as e:
            logger.error(f"Failed to rewrite checklist: {e}")
            
    return completed_count

def parse_creation_date(content: str) -> datetime.date | None:
    """Fallback extraction of creation date if not in YAML."""
    match = re.search(r'创建时间:\s*(\d{4}-\d{2}-\d{2})', content)
    if match:
        return datetime.datetime.strptime(match.group(1), "%Y-%m-%d").date()
    return None

def calculate_sm2(ease: float, interval: int, score: int) -> tuple[float, int]:
    """
    SuperMemo-2 Algorithm.
    score: 0-5 (0: Blackout, 3: Hard, 4: Good, 5: Easy)
    """
    if score < 3:
        # Failed or barely remembered, reset interval
        new_interval = 1
    else:
        if interval == 0:
            new_interval = 1
        elif interval == 1:
            new_interval = 6
        else:
            new_interval = round(interval * ease)
            
    new_ease = ease + (0.1 - (5.0 - score) * (0.08 + (5.0 - score) * 0.02))
    new_ease = max(1.3, new_ease) # Ease should not drop below 1.3
    
    return round(new_ease, 2), new_interval

def enhance_due_cards(due_cards, all_files_with_paths):
    """
    Enhance cards that are due today by finding hidden connections
    with other cards in the vault and injecting them directly into the markdown.
    """
    if not due_cards:
        return
        
    logger.info("🧠 Running AI Auto-Enhancer on due cards...")
    
    # 1. Extract info for all valid cards
    all_cards = []
    for fname, fpath in all_files_with_paths:
        info = extract_card_info(fpath)
        if info:
            all_cards.append(info)
            
    if len(all_cards) < 2:
        return
        
    # 2. Generate embeddings
    texts_to_embed = [c['core'][:500] for c in all_cards]
    embeddings = generate_embeddings(texts_to_embed)
    
    import time
    
    for due_card in due_cards:
        due_idx = -1
        for i, c in enumerate(all_cards):
            if c['filepath'] == due_card['filepath']:
                due_idx = i
                break
                
        if due_idx == -1:
            continue
            
        due_info = all_cards[due_idx]
        best_sim = -1
        best_target = None
        
        for j, target_info in enumerate(all_cards):
            if j == due_idx:
                continue
                
            # Skip if already linked in the file (either manually or by previous AI runs)
            if target_info['filename'].replace('.md', '') in due_info['links']:
                continue
                
            sim = cosine_similarity(embeddings[due_idx], embeddings[j])
            if sim > best_sim and sim >= SIMILARITY_THRESHOLD:
                best_sim = sim
                best_target = target_info
                
        if best_target:
            logger.info(f"Enhancing '{due_info['title']}' with connection to '{best_target['title']}' (Sim: {best_sim:.2f})")
            
            prompt = f"""
            You are an elite Knowledge Graph Architect. 
            The user is about to review Card A. 
            I found a hidden structural connection between Card A and Card B.
            
            Card A: {due_info['title']}
            Content: {due_info['core'][:800]}
            
            Card B: {best_target['title']}
            Content: {best_target['core'][:800]}
            
            Task: Write a deep, 50-100 word insightful diagnosis explaining the hidden causal chain, 
            fundamental law, or complementary perspective between them. 
            Do not greet or explain what you are doing, just provide the direct insight.
            Output JSON strictly.
            """
            try:
                response = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=types.Schema(
                            type=types.Type.OBJECT,
                            properties={"insight": types.Schema(type=types.Type.STRING, description="深度洞见与因果链条分析（中文）")},
                            required=["insight"]
                        ),
                        temperature=0.4
                    )
                )
                
                raw_text = response.text.strip()
                if raw_text.startswith("```json"): raw_text = raw_text[7:]
                if raw_text.startswith("```"): raw_text = raw_text[3:]
                if raw_text.endswith("```"): raw_text = raw_text[:-3]
                
                data = json.loads(raw_text.strip())
                insight = data.get('insight')
                
                if insight:
                    target_link = f"[[{best_target['filename'].replace('.md', '')}]]"
                    injection = f"\n\n## 🌐 AI 自动发现的关联\n**发现因果链条/跨界视角**：{target_link}\n> {insight}\n"
                    
                    with open(due_info['filepath'], "a", encoding="utf-8") as f:
                        f.write(injection)
                        
                    logger.info(f"✅ Injected AI connection into {due_info['title']}")
                    time.sleep(4) # rate limit
            except Exception as e:
                logger.error(f"Failed to generate auto-enhancement for {due_info['title']}: {e}")

def save_review_checklist(today: datetime.date, due_cards: list) -> str:
    """Helper to generate and save daily review markdown note and send desktop notification."""
    today_str = today.strftime("%Y-%m-%d")
    content = f"""---
创建时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
类型: 间隔复习
标签: #复习 #SM-2 #AI生成
---
# 🧠 SM-2 动态复习清单 — {today_str}

> 基于**SM-2 动态自适应算法**生成。今日精选 **{len(due_cards)}** 张核心卡片（已启用防爆仓限额与关机堆积自动平摊）。
> 
> 💡 **极简打卡（零负担）**：
> 1. 打开下方卡片，花 1~2 分钟扫一眼核心要点或 If-Then 战备触发器。
> 2. **直接在下方清单打勾 `- [x]`**。
> 3. 后台会自动检测并将该卡片的复习间隔**翻倍（x2）推进到未来**，彻底告别反人类的 YAML 属性填分！

## 🎯 今日待复习

"""
    for card in due_cards:
        content += f"- [ ] [[{card['title']}]] (当前间隔: {card['interval']}天, 简易度: {card['ease']})\n"
        
    os.makedirs(REVIEW_DIR, exist_ok=True)
    filepath = os.path.join(REVIEW_DIR, f"间隔复习_{today_str}.md")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
        
    logger.info(f"✅ SM-2 Review list saved and synced: {filepath}")
    
    # Trigger Desktop Notification
    try:
        notification.notify(
            title='🧠 AI Brain 复习提醒',
            message=f'今天精选 {len(due_cards)} 张知识卡片需要重温（自动限额7张）！请前往 Obsidian 查看。',
            app_name='AI Brain',
            timeout=10
        )
        logger.info("Sent desktop toast notification.")
    except Exception as e:
        logger.warning(f"Failed to send desktop notification: {e}")
        
    return filepath

def process_spaced_review_fast(engine) -> str | None:
    """AuraMemory-accelerated SM-2 review processor (<1ms query)."""
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    processed_scores = 0
    
    # 0. Process any checked items in today's review checklist (auto-complete checked cards)
    today_review_path = os.path.join(REVIEW_DIR, f"间隔复习_{today_str}.md")
    process_checklist_completions(today_review_path, today, engine=engine)
    
    # 1. Process pending sm2_scores using SQLite query
    with engine.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT file_path, frontmatter_json, sm2_ease, sm2_interval
            FROM memory_ledger
            WHERE json_extract(frontmatter_json, '$.sm2_score') IS NOT NULL
              AND json_extract(frontmatter_json, '$.sm2_score') != ''
        """)
        scored_cards = cursor.fetchall()
        
    for row in scored_cards:
        fpath = row['file_path']
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)
            score = post.metadata.get('sm2_score')
            if score is not None and str(score).strip() != "":
                score = int(score)
                if 0 <= score <= 5:
                    ease = float(row['sm2_ease'])
                    interval = int(row['sm2_interval'])
                    new_ease, new_interval = calculate_sm2(ease, interval, score)
                    next_review_date = today + datetime.timedelta(days=new_interval)
                    
                    post.metadata['sm2_ease'] = new_ease
                    post.metadata['sm2_interval'] = new_interval
                    post.metadata['sm2_next_review'] = next_review_date.strftime("%Y-%m-%d")
                    post.metadata['sm2_score'] = None
                    
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(frontmatter.dumps(post))
                    
                    from aura_memory.parser import parse_markdown_file
                    record = parse_markdown_file(fpath)
                    if record:
                        engine.db.upsert_record(record)
                    processed_scores += 1
        except Exception as e:
            logger.error(f"Failed to update score for {fpath}: {e}")
            
    if processed_scores > 0:
        logger.info(f"⚡ AuraMemory processed {processed_scores} user review scores.")
        
    # 2. Get due reviews in <1ms
    due_items = engine.get_due_reviews(today_str, categories=["skills", "insights"])
    if not due_items:
        logger.info("✅ No cards due for review today. Your brain is up to date!")
        return None
        
    logger.info(f"📋 Found {len(due_items)} cards due for review today via AuraMemory!")
    
    due_cards = [
        {
            "title": item.title,
            "interval": item.sm2_interval,
            "ease": item.sm2_ease,
            "filepath": item.file_path
        }
        for item in due_items
    ]
    
    # Apply Anti-Snowball Staggering & Capping (Max 7)
    due_cards = stagger_and_cap_due_cards(due_cards, today, engine=engine, max_daily=MAX_DAILY_REVIEWS)
    
    # Extract paths for AI auto-enhancer
    with engine.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, file_path FROM memory_ledger WHERE category IN ('skills', 'insights') AND title NOT LIKE '[已合并]%'")
        all_files_with_paths = [(r['title'] + '.md', r['file_path']) for r in cursor.fetchall()]
        
    enhance_due_cards(due_cards, all_files_with_paths)
    due_cards.sort(key=lambda x: x["interval"])
    return save_review_checklist(today, due_cards)

def process_spaced_review():
    """Main entry point: process scores, calculate next review, generate list, notify."""
    logger.info("🧠 Starting SM-2 Spaced Repetition Scheduler...")
    
    # Try AuraMemory fast path first
    try:
        from aura_memory.engine import get_engine
        engine = get_engine()
        if engine and engine.db:
            return process_spaced_review_fast(engine)
    except Exception as e:
        logger.warning(f"AuraMemory fast path failed, falling back to disk traversal: {e}")
    
    if not os.path.exists(SKILLS_DIR) and not os.path.exists(INSIGHTS_DIR):
        logger.warning(f"Neither Skills nor Insights directory found.")
        return None
        
    all_files_with_paths = []
    
    if os.path.exists(SKILLS_DIR):
        for f in os.listdir(SKILLS_DIR):
            if f.endswith('.md') and not f.startswith('[已合并]') and not f.startswith('[桥接]'):
                all_files_with_paths.append((f, os.path.join(SKILLS_DIR, f)))
                
    if os.path.exists(INSIGHTS_DIR):
        for f in os.listdir(INSIGHTS_DIR):
            if f.endswith('.md'):
                all_files_with_paths.append((f, os.path.join(INSIGHTS_DIR, f)))
    
    today = datetime.date.today()
    due_cards = []
    processed_scores = 0
    
    for fname, fpath in all_files_with_paths:
        
        try:
            # Load Markdown file with frontmatter
            with open(fpath, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)
                
            needs_save = False
            
            # Initialize SM-2 fields if they don't exist
            if 'sm2_ease' not in post.metadata:
                post.metadata['sm2_ease'] = 2.5
                post.metadata['sm2_interval'] = 0
                
                # If it's a new card, set next review to tomorrow or today based on creation
                creation_date_str = post.metadata.get('date_created') or post.metadata.get('创建时间')
                if creation_date_str and isinstance(creation_date_str, str):
                    try:
                         # Handle datetime or date strings
                         c_date = datetime.datetime.strptime(creation_date_str[:10], "%Y-%m-%d").date()
                    except:
                         c_date = today
                else:
                    c_date = parse_creation_date(post.content) or today
                    
                post.metadata['sm2_next_review'] = (c_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                post.metadata['sm2_score'] = None
                needs_save = True
                
            # Process User Feedback Score
            score = post.metadata.get('sm2_score')
            if score is not None and str(score).strip() != "":
                try:
                    score = int(score)
                    if 0 <= score <= 5:
                        ease = float(post.metadata.get('sm2_ease', 2.5))
                        interval = int(post.metadata.get('sm2_interval', 0))
                        
                        new_ease, new_interval = calculate_sm2(ease, interval, score)
                        next_review_date = today + datetime.timedelta(days=new_interval)
                        
                        post.metadata['sm2_ease'] = new_ease
                        post.metadata['sm2_interval'] = new_interval
                        post.metadata['sm2_next_review'] = next_review_date.strftime("%Y-%m-%d")
                        post.metadata['sm2_score'] = None # Reset score
                        
                        logger.info(f"Updated SM-2 for {fname}: Score={score} -> Next={next_review_date}, Ease={new_ease}")
                        needs_save = True
                        processed_scores += 1
                except ValueError:
                    logger.warning(f"Invalid sm2_score in {fname}: {score}")
                    
            if needs_save:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(frontmatter.dumps(post))
                    f.flush()
                    os.fsync(f.fileno())
                    
            # Check if due for review
            next_review_str = post.metadata.get('sm2_next_review')
            if next_review_str:
                try:
                    next_review = datetime.datetime.strptime(next_review_str[:10], "%Y-%m-%d").date()
                    if next_review <= today:
                        due_cards.append({
                            "title": fname.replace('.md', ''),
                            "interval": post.metadata.get('sm2_interval', 0),
                            "ease": post.metadata.get('sm2_ease', 2.5),
                            "filepath": fpath
                        })
                except Exception as e:
                    logger.debug(f"Date parse error in {fname}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to process SM-2 for {fname}: {e}")
            
    logger.info(f"Processed {processed_scores} user scores.")
    
    if not due_cards:
        logger.info("✅ No cards due for review today. Your brain is up to date!")
        return None
        
    logger.info(f"📋 Found {len(due_cards)} cards due for review today!")
    
    # Apply Anti-Snowball Staggering & Capping (Max 7)
    due_cards = stagger_and_cap_due_cards(due_cards, today, engine=None, max_daily=MAX_DAILY_REVIEWS)
    
    # Run the AI Enhancer
    enhance_due_cards(due_cards, all_files_with_paths)
    
    # Sort due cards by interval (newer cards first)
    due_cards.sort(key=lambda x: x["interval"])
    return save_review_checklist(today, due_cards)

