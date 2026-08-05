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
from config import SKILLS_DIR, OBSIDIAN_BASE_PATH

logger = logging.getLogger(__name__)

REVIEW_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每日复习")

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

def process_spaced_review():
    """Main entry point: process scores, calculate next review, generate list, notify."""
    logger.info("🧠 Starting SM-2 Spaced Repetition Scheduler...")
    
    if not os.path.exists(SKILLS_DIR):
        logger.warning(f"Skills directory not found: {SKILLS_DIR}")
        return None
        
    all_files = [
        f for f in os.listdir(SKILLS_DIR)
        if f.endswith('.md') and not f.startswith('[已合并]') and not f.startswith('[桥接]')
    ]
    
    today = datetime.date.today()
    due_cards = []
    processed_scores = 0
    
    for fname in all_files:
        fpath = os.path.join(SKILLS_DIR, fname)
        
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
                            "ease": post.metadata.get('sm2_ease', 2.5)
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
    
    # Sort due cards by interval (newer cards first)
    due_cards.sort(key=lambda x: x["interval"])
    
    # Generate Review Checklist
    today_str = today.strftime("%Y-%m-%d")
    content = f"""---
创建时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
类型: 间隔复习
标签: #复习 #SM-2 #AI生成
---
# 🧠 SM-2 动态复习清单 — {today_str}

> 基于**SM-2 动态自适应算法**生成。今日共有 **{len(due_cards)}** 张知识卡片需要复习。
> 
> 💡 **复习方法**：
> 1. 打开下方卡片，尝试回忆核心概念。
> 2. 在该卡片的 **YAML 属性面板 (Properties)** 中，找到 `sm2_score` 字段。
> 3. 填入你的真实记忆评分：
>    - `5`: 太简单了 (Easy)
>    - `4`: 顺利回忆 (Good)
>    - `3`: 有点吃力 (Hard)
>    - `0`: 完全忘记 (Blackout)
> 4. 算法会在明天自动收集分数，并为你量身定制下次复习时间！

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
            message=f'今天有 {len(due_cards)} 张知识卡片需要重温！请前往 Obsidian 查看。',
            app_name='AI Brain',
            timeout=10
        )
        logger.info("Sent desktop toast notification.")
    except Exception as e:
        logger.warning(f"Failed to send desktop notification: {e}")
        
    return filepath
