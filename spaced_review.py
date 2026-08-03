"""
Spaced Repetition Scheduler
Scans the skill library, parses creation dates from YAML frontmatter,
and generates a daily review checklist based on Ebbinghaus forgetting curve intervals.
"""

import os
import re
import logging
from datetime import datetime, date
from config import SKILLS_DIR, OBSIDIAN_BASE_PATH

logger = logging.getLogger(__name__)

# Ebbinghaus forgetting curve review intervals (days after creation)
REVIEW_INTERVALS = [1, 3, 7, 14, 30, 60, 180]

# Output directory for review lists
REVIEW_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每日复习")


def parse_creation_date(filepath: str) -> date | None:
    """Extract creation date from YAML frontmatter of a skill card."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(500)  # Only need the frontmatter
        
        # Match 创建时间: YYYY-MM-DD or YYYY-MM-DD HH:MM
        match = re.search(r'创建时间:\s*(\d{4}-\d{2}-\d{2})', content)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except Exception as e:
        logger.debug(f"Could not parse date from {filepath}: {e}")
    return None


def get_review_stage(days_since_creation: int) -> tuple[int, str] | None:
    """
    Determine if today is a review day based on Ebbinghaus intervals.
    Returns (interval, label) if review is due, None otherwise.
    Allows ±1 day tolerance for each interval.
    """
    for interval in REVIEW_INTERVALS:
        if abs(days_since_creation - interval) <= 1:
            labels = {
                1: "📕 第1天复习（短期记忆巩固）",
                3: "📗 第3天复习（初步编码加固）",
                7: "📘 第7天复习（一周强化记忆）",
                14: "📙 第14天复习（两周深度巩固）",
                30: "📓 第30天复习（月度长期记忆）",
                60: "📔 第60天复习（两月终极巩固）",
                180: "🏆 第180天复习（半年终极检验）",
            }
            return interval, labels.get(interval, f"第{interval}天复习")
    return None


def scan_for_reviews() -> dict[str, list[dict]]:
    """
    Scan all skill cards and group today's review items by review stage.
    Returns dict mapping stage_label -> list of card info dicts.
    """
    today = date.today()
    reviews: dict[str, list[dict]] = {}
    
    if not os.path.exists(SKILLS_DIR):
        logger.warning(f"Skills directory not found: {SKILLS_DIR}")
        return reviews
    
    all_files = [
        f for f in os.listdir(SKILLS_DIR)
        if f.endswith('.md') and not f.startswith('[已合并]')
    ]
    
    scanned = 0
    for fname in all_files:
        fpath = os.path.join(SKILLS_DIR, fname)
        creation_date = parse_creation_date(fpath)
        
        if not creation_date:
            continue
        
        scanned += 1
        days_diff = (today - creation_date).days
        
        result = get_review_stage(days_diff)
        if result:
            interval, label = result
            if label not in reviews:
                reviews[label] = []
            
            # Extract title from filename
            title = fname.replace('.md', '')
            reviews[label].append({
                "filename": fname,
                "title": title,
                "creation_date": creation_date.strftime("%Y-%m-%d"),
                "days_ago": days_diff,
                "interval": interval
            })
    
    logger.info(f"Scanned {scanned} cards with valid dates. Found {sum(len(v) for v in reviews.values())} cards due for review.")
    return reviews


def generate_review_note(reviews: dict[str, list[dict]]) -> str | None:
    """Generate a Markdown review checklist."""
    if not reviews:
        return None
    
    today_str = date.today().strftime("%Y-%m-%d")
    total = sum(len(v) for v in reviews.values())
    
    content = f"""---
创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
类型: 间隔复习
标签: #复习 #艾宾浩斯 #AI生成
---
# 🧠 间隔复习清单 — {today_str}

> 基于**艾宾浩斯遗忘曲线**自动生成。今日共有 **{total}** 张知识卡片需要复习。
> 
> 复习方法：打开卡片 → 先尝试回忆核心概念 → 再对照原文 → 勾选完成

"""
    
    # Sort by interval (short-term first)
    sorted_stages = sorted(reviews.items(), key=lambda x: x[1][0]["interval"])
    
    for label, cards in sorted_stages:
        content += f"## {label}\n"
        for card in cards:
            content += f"- [ ] [[{card['title']}]]（创建于 {card['creation_date']}，{card['days_ago']} 天前）\n"
        content += "\n"
    
    content += """---
## 📊 复习进度追踪

| 阶段 | 间隔 | 记忆保留率 |
|------|------|-----------|
| 📕 第1天 | 24h | ~33% → 80%+ |
| 📗 第3天 | 72h | ~25% → 85%+ |
| 📘 第7天 | 1周 | ~20% → 90%+ |
| 📙 第14天 | 2周 | ~15% → 92%+ |
| 📓 第30天 | 1月 | ~10% → 95%+ |
| 📔 第60天 | 2月 | ~5% → 97%+ |
| 🏆 第180天 | 半年 | 终极检验 → 永久记忆 |

> 💡 每次复习后，记忆保留率会显著回升。坚持间隔复习，知识会从短期记忆转化为永久记忆。
"""
    return content


def process_spaced_review():
    """Main entry point: scan, schedule, and generate today's review list."""
    logger.info("🧠 Starting Spaced Repetition Scheduler...")
    
    reviews = scan_for_reviews()
    
    if not reviews:
        logger.info("✅ No cards due for review today. Your brain is up to date!")
        return None
    
    total = sum(len(v) for v in reviews.values())
    logger.info(f"📋 Found {total} cards due for review today!")
    
    # Generate review note
    content = generate_review_note(reviews)
    if not content:
        return None
    
    # Save to review directory
    os.makedirs(REVIEW_DIR, exist_ok=True)
    
    today_str = date.today().strftime("%Y-%m-%d")
    filename = f"间隔复习_{today_str}.md"
    filepath = os.path.join(REVIEW_DIR, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    
    logger.info(f"✅ Review list saved and synced: {filepath}")
    return filepath
