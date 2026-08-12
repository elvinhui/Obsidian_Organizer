import os
import re
import json
import logging
import time
import random
from datetime import datetime
from google import genai
from google.genai import types
import genanki
from config import GEMINI_API_KEY, SKILLS_DIR, ANKI_DIR

logger = logging.getLogger(__name__)
client = genai.Client(api_key=GEMINI_API_KEY)

# Define the Anki Model
ANKI_MODEL_ID = 1607392319
ANKI_MODEL = genanki.Model(
    ANKI_MODEL_ID,
    'Obsidian AI Brain Q&A',
    fields=[
        {'name': 'Question'},
        {'name': 'Answer'},
        {'name': 'Source'},
    ],
    templates=[
        {
            'name': 'Card 1',
            'qfmt': '<h2>{{Question}}</h2>',
            'afmt': '{{FrontSide}}<hr id="answer"><div style="text-align: left;">{{Answer}}</div><br><br><small style="color: gray;"><i>来源: {{Source}}</i></small>',
        },
    ],
    css="""
    .card {
        font-family: 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 16px;
        text-align: center;
        color: #e0e0e0;
        background-color: #1e1e1e;
        line-height: 1.6;
        padding: 20px;
    }
    h2 {
        color: #ffffff;
        margin-bottom: 20px;
    }
    hr#answer {
        border: 0;
        border-top: 1px solid #444;
        margin: 20px 0;
    }
    """
)


def get_pending_cards() -> list[dict]:
    """Scans the skills directory for cards marked for review."""
    cards = []
    
    if not os.path.isdir(SKILLS_DIR):
        logger.warning(f"Skills directory not found: {SKILLS_DIR}")
        return cards

    for filename in os.listdir(SKILLS_DIR):
        if not filename.endswith(".md"):
            continue
            
        filepath = os.path.join(SKILLS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Check for the status "⏳ 待复习"
            if "状态: ⏳ 待复习" in content:
                cards.append({
                    "filepath": filepath,
                    "filename": filename,
                    "title": filename.replace(".md", ""),
                    "content": content
                })
        except Exception as e:
            logger.error(f"Failed to read skill card {filepath}: {e}")
            
    return cards


def generate_qa_pairs(card: dict) -> list[dict]:
    """Uses Gemini to generate Q&A pairs from a card."""
    prompt = f"""你是一位专业的知识管理与学习教练。
请基于以下笔记内容，提取出最核心的概念和知识点，并设计 3-5 个用于 Anki 间隔重复的问答卡片（Q&A）。

要求：
1. 问题（Question）必须简洁明确。
2. 答案（Answer）必须精准，可以是核心要点或项目符号，便于记忆。
3. 请严格输出为 JSON 数组格式，格式如下：
[
    {{"question": "问题1", "answer": "答案1"}},
    {{"question": "问题2", "answer": "答案2"}}
]

不要输出任何其他解释性文字，只输出合法的 JSON 数组。

笔记标题：{card['title']}
笔记内容：
{card['content']}
"""
    
    max_retries = 3
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3
                )
            )
            break
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"]):
                delay = (2 ** attempt) * 5
                logger.warning(f"Gemini API limit hit. Retrying in {delay}s (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
            else:
                raise

    if not response:
        logger.error(f"Failed to generate Q&A for {card['title']}")
        return []

    text = response.text.strip()
    
    # Clean up markdown JSON blocks if present
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    try:
        qa_pairs = json.loads(text.strip())
        return qa_pairs
    except Exception as e:
        logger.error(f"Failed to parse JSON for {card['title']}: {e}\nRaw text: {text}")
        return []


def mark_card_as_processed(filepath: str):
    """Updates the status in the card to indicate flashcards were generated."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        new_content = content.replace("状态: ⏳ 待复习", "状态: 🔄 间隔重复中")
            
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        logger.error(f"Failed to mark card {filepath} as processed: {e}")


def process_anki_generation():
    """Main entry point to convert pending skill cards to an Anki deck."""
    logger.info("🧠 Scanning Skills library for Anki generation...")
    cards = get_pending_cards()
    
    if not cards:
        logger.info("No pending cards for Anki generation.")
        return
        
    logger.info(f"🚀 Found {len(cards)} card(s) to convert to Anki flashcards.")
    
    deck_id = random.randrange(1 << 30, 1 << 31)
    deck = genanki.Deck(deck_id, f'Obsidian AI Brain 知识卡片 ({datetime.now().strftime("%Y-%m-%d")})')
    
    notes_added = 0
    
    for card in cards:
        logger.info(f"Generating Q&A for card: {card['title']}...")
        qa_pairs = generate_qa_pairs(card)
        
        if not qa_pairs:
            continue
            
        for idx, qa in enumerate(qa_pairs):
            q = qa.get("question", "").replace('\n', '<br>')
            a = qa.get("answer", "").replace('\n', '<br>')
            if not q or not a:
                continue
                
            # Create a unique but stable guid based on the title and question index
            guid = genanki.guid_for(card['title'], q)
            
            note = genanki.Note(
                model=ANKI_MODEL,
                fields=[q, a, card['title']],
                guid=guid
            )
            deck.add_note(note)
            notes_added += 1
            
        # Update the file status so it's not processed again
        mark_card_as_processed(card['filepath'])
        
    if notes_added > 0:
        os.makedirs(ANKI_DIR, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        apkg_filename = f"AI_Flashcards_{date_str}.apkg"
        apkg_filepath = os.path.join(ANKI_DIR, apkg_filename)
        
        genanki.Package(deck).write_to_file(apkg_filepath)
        logger.info(f"✅ Generated {notes_added} Anki flashcards. Saved to {apkg_filepath}")
        
        # Obsidian doesn't show .apkg files natively, so we create a companion .md file
        md_filename = f"Anki卡包_{date_str}.md"
        md_filepath = os.path.join(ANKI_DIR, md_filename)
        
        # URI encode the path for the Obsidian link
        import urllib.parse
        encoded_path = urllib.parse.quote(apkg_filepath.replace('\\', '/'))
        
        md_content = f"""---
创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
标签: #Anki #间隔重复
本次生成卡片数: {notes_added}
---
# 🧠 Anki 智能卡包 ({datetime.now().strftime("%Y-%m-%d")})

> 本次共为你从技能库中提取并生成了 **{notes_added}** 张记忆卡片！

## 📥 导入方法
由于 Obsidian 默认不显示 `.apkg` 文件，请直接点击下方链接导入到 Anki：

👉 **[点击这里打开并导入 Anki 卡包](file:///{encoded_path})**

*(如果点击没反应，可以在文件资源管理器中打开此目录 `{ANKI_DIR}` 双击导入)*
"""
        try:
            with open(md_filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
        except Exception as e:
            logger.error(f"Failed to create markdown wrapper for Anki package: {e}")
            
    else:
        logger.info("No flashcards were successfully generated.")
