import os
import re
import logging
import time
from datetime import datetime, timedelta
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, SKILLS_DIR, OBSIDIAN_BASE_PATH, OPEN_QUESTIONS_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

DIGEST_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每日复盘")


def get_recent_skill_cards(days: int = 1) -> list[dict]:
    """Reads all skill cards created within the last N days."""
    cards = []
    cutoff = datetime.now() - timedelta(days=days)

    if not os.path.isdir(SKILLS_DIR):
        return cards

    for filename in os.listdir(SKILLS_DIR):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(SKILLS_DIR, filename)
        try:
            mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            if mod_time >= cutoff:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                cards.append({
                    "filename": filename,
                    "content": content,
                    "modified": mod_time.strftime("%Y-%m-%d %H:%M")
                })
        except Exception as e:
            logger.warning(f"Could not read {filepath}: {e}")

    return cards


def get_existing_open_questions() -> list[str]:
    """Reads titles of existing open questions to avoid duplication."""
    existing = []
    if not os.path.isdir(OPEN_QUESTIONS_DIR):
        return existing
        
    for filename in os.listdir(OPEN_QUESTIONS_DIR):
        if filename.endswith(".md"):
            # Clean up the filename to just get the core topic
            topic = filename.replace("💭 开放性思考：", "").replace(".md", "").replace("开放问题_", "")
            existing.append(topic)
    return existing

def generate_digest(cards: list[dict]) -> str:
    """Sends all recent cards to Gemini for cross-analysis and digest generation."""
    cards_text = "\n\n---\n\n".join(
        [f"### {c['filename']} (修改于 {c['modified']})\n{c['content']}" for c in cards]
    )

    existing_qs = get_existing_open_questions()
    avoid_str = ""
    if existing_qs:
        qs_list = "\n- ".join(existing_qs[:30]) # Pass up to 30 recent topics
        avoid_str = f"\n\n⚠️ **防重叠警告**：用户已经积累了以下开放性问题（或高度相似的命题），请务必提出**全新视角**的问题，绝对不要与以下内容重叠：\n- {qs_list}"

    prompt = f"""你是一位顶级的个人知识管理教练。以下是用户今天新生成/更新的知识技能卡片。

请完成以下任务：

1. **📊 今日知识主题概览**：列出今天学了哪些主题，按分类统计（认知提升/财商知识/AI技术/其他）
2. **🔗 跨卡片隐藏关联**：深度分析不同卡片之间的隐藏联系、共同底层逻辑、互补观点或矛盾观点（这是最重要的部分）
3. **💡 核心洞察提炼**：从所有卡片中提炼出 3-5 个最有价值的核心洞察
4. **🎯 本周可执行行动**：基于今天学到的知识，给出 3 个具体的、可立即执行的行动项
5. **🤔 开放性思考**：提出 2-3 个值得进一步探索的问题（请提出具体的场景化或边界探讨问题）{avoid_str}

输出格式为 Markdown，使用中文，风格要有深度但不冗长。

今日知识卡片：
{cards_text}
"""

    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.5
                )
            )
            break
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"]):
                delay = (2 ** attempt) * 15
                logger.warning(f"Gemini API limit hit. Retrying in {delay}s (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
            else:
                raise

    if not response:
        raise Exception("Max retries exceeded for daily digest generation.")

    return response.text


def extract_and_save_open_questions(digest_text: str):
    """Parses open questions from the digest and creates individual .md files."""
    # Find the section "开放性思考" (matches ##, ###, or bold)
    match = re.search(r'(?:#{2,4}|\*\*).*?开放性思考.*?\n(.*?)(?:---|#{2,4}|$)', digest_text, re.DOTALL)
    if not match:
        logger.warning("Could not find '开放性思考' section in digest.")
        return

    section_text = match.group(1).strip()
    
    # Match bullet points: *, -, or 1. 
    bullet_pattern = re.compile(r'^[\*\-\d\.]+\s+(.*)', re.MULTILINE)
    questions = bullet_pattern.findall(section_text)

    if not questions:
        logger.warning("No questions found in '开放性思考' section.")
        return

    os.makedirs(OPEN_QUESTIONS_DIR, exist_ok=True)
    
    for q in questions:
        # Extract title from before the colon, handling optional bold ** 
        title_match = re.search(r'^(?:\*\*)?(.*?)(?:\*\*)?[：:]\s*(.*)', q)
        if title_match:
            raw_title = title_match.group(1).strip()
            # If the title is too long, it might not be a real title. Fallback.
            if len(raw_title) < 40:
                safe_title = re.sub(r'[\\/*?:"<>|]', "", raw_title)
                title = safe_title
            else:
                safe_title = re.sub(r'[\\/*?:"<>|]', "", q[:15])
                title = f"开放问题_{safe_title}"
        else:
            safe_title = re.sub(r'[\\/*?:"<>|]', "", q[:15])
            title = f"开放问题_{safe_title}"
            
        filename = f"💭 开放性思考：{title}.md"
        filepath = os.path.join(OPEN_QUESTIONS_DIR, filename)

        if not os.path.exists(filepath):
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            # Strip markdown bold syntax from question for cleaner reading
            clean_question = q.replace("**", "")
            content = f"""---
创建时间: {now}
标签: #深度思考 #认知复盘
状态: 持续迭代
---
# 💭 开放性思考：{title}

## ❓ 命题重述 (The Prompt)
> **当前思考的问题是：**
> {clean_question}

## 🎯 核心破局点 (My Stance)
> **一句话回答：** 

## 🛠️ 现实映射与论证 (Reality Check)
- **破局逻辑 (为什么这么想)：**
- **现实映射 (结合我当前的实际场景)：**
  - 

## 👣 48小时落地动作 (Next Action)
> *教练寄语：“挑选一个最让你产生共鸣的卡片，在接下来的 48 小时内落地实践即可。”*
- [ ] 
"""
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                logger.info(f"✅ Created and synced open question: {filename}")
            except Exception as e:
                logger.error(f"Failed to create {filename}: {e}")

def generate_and_save_digest(days: int = 1) -> str | None:
    """Main entry point: scan recent cards, generate digest, save to vault."""
    logger.info(f"📰 Scanning skill cards from the last {days} day(s)...")
    cards = get_recent_skill_cards(days=days)

    if not cards:
        logger.info("No recent skill cards found. Skipping digest generation.")
        return None

    logger.info(f"📚 Found {len(cards)} recent card(s). Generating digest...")
    digest_content = generate_digest(cards)

    # Build final markdown
    now = datetime.now()
    date_display = now.strftime("%Y-%m-%d")
    card_list = "\n".join([f"  - [[{c['filename'].replace('.md', '')}]]" for c in cards])

    header = f"""---
创建时间: {now.strftime("%Y-%m-%d %H:%M")}
类型: 每日复盘
标签: #日报 #AI生成 #知识复盘
关联卡片:
{card_list}
---
# 📰 知识日报 — {date_display}

> 今日共处理 **{len(cards)}** 张知识卡片，以下是 AI 生成的交叉分析与行动建议。

"""

    full_content = header + digest_content

    # Save
    os.makedirs(DIGEST_DIR, exist_ok=True)
    filename = f"知识日报_{date_display}.md"
    filepath = os.path.join(DIGEST_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)
        f.flush()
        os.fsync(f.fileno())

    logger.info(f"✅ Daily digest saved and synced: {filepath}")
    
    # Automatically extract and save open questions
    try:
        extract_and_save_open_questions(digest_content)
    except Exception as e:
        logger.error(f"Error parsing open questions: {e}")
        
    return filepath
