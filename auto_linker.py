"""
Auto-Linker Module
Scans the skill library, uses Gemini to discover semantic relationships
between knowledge cards, and automatically inserts Obsidian [[双链]] links.
This brings the Obsidian Graph View to life.
"""

import os
import re
import json
import time
import logging
from google import genai
from google.genai import types
from config import SKILLS_DIR, GEMINI_API_KEY

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

# Max cards to process per Gemini call (to stay within token limits)
BATCH_SIZE = 30


def extract_card_summary(filepath: str) -> dict | None:
    """Extract title and core concepts from a skill card for relationship analysis."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract title (first # heading)
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else os.path.basename(filepath)
        
        # Extract core concepts section
        core_match = re.search(
            r'##\s*💡.*?\n(.*?)(?=\n##|\Z)', content, re.DOTALL
        )
        core = core_match.group(1).strip()[:300] if core_match else ""
        
        # Extract action/SOP section
        action_match = re.search(
            r'##\s*🛠️.*?\n(.*?)(?=\n##|\Z)', content, re.DOTALL
        )
        action = action_match.group(1).strip()[:200] if action_match else ""
        
        # Extract existing links to avoid duplicates
        existing_links = set(re.findall(r'\[\[(.+?)\]\]', content))
        
        return {
            "filename": os.path.basename(filepath),
            "title": title,
            "core": core,
            "action": action,
            "existing_links": existing_links
        }
    except Exception as e:
        logger.error(f"Failed to extract summary from {filepath}: {e}")
        return None


def find_relationships_with_gemini(cards: list[dict]) -> list[dict]:
    """
    Uses Gemini to analyze a batch of skill cards and discover relationships.
    Returns a list of link recommendations.
    """
    # Build the card index for Gemini
    card_index = ""
    for i, card in enumerate(cards):
        card_index += f"\n[{i+1}] 文件: {card['filename']}\n    标题: {card['title']}\n    核心: {card['core'][:200]}\n    行动: {card['action'][:150]}\n"
    
    prompt = f"""你是一位知识图谱构建专家。以下是一批 Obsidian 知识卡片的摘要信息。
请分析它们之间的语义关系，找出有意义的连接。

关系类型：
1. **概念重叠**: 两张卡片讨论了相同的核心概念（如"复利思维"同时出现在多张卡片中）
2. **因果链条**: 一张卡片的内容是另一张的前因或后果（如"大脑重塑" → "习惯养成"）
3. **互补视角**: 两张卡片从不同角度讨论同一主题（如投资和心理学对"风险"的不同理解）
4. **对立观点**: 两张卡片持有对立或矛盾的立场

要求：
- 只返回真正有价值的关联（相似度极高的重复卡片不算，那是去重问题）
- 每个关系附上一句话说明为什么它们相关
- 以 JSON 格式返回

JSON 格式：
{{
  "links": [
    {{
      "source": "源文件名.md",
      "target": "目标文件名.md", 
      "type": "概念重叠|因果链条|互补视角|对立观点",
      "reason": "一句话说明关联原因"
    }}
  ]
}}

知识卡片列表：
{card_index}
"""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            result = json.loads(response.text)
            return result.get("links", [])
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED"]):
                delay = (2 ** attempt) * 15
                logger.warning(f"Gemini rate limit. Retrying in {delay}s. Error: {err_str}")
                time.sleep(delay)
            else:
                logger.error(f"Gemini link analysis failed: {e}")
                return []
    return []


def insert_links_into_card(filepath: str, links: list[dict], all_titles: dict):
    """
    Insert [[双链]] links into a card's 🔗 Connections section.
    
    Args:
        filepath: Path to the skill card
        links: List of link dicts with 'target', 'type', 'reason'
        all_titles: Dict mapping filename -> display title
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Find existing [[links]] to avoid duplicates
        existing_links = set(re.findall(r'\[\[(.+?)\]\]', content))
        
        # Build new link entries
        new_entries = []
        for link in links:
            target_file = link["target"].replace(".md", "")
            if target_file in existing_links:
                continue  # Skip already linked
            
            link_type = link.get("type", "关联")
            reason = link.get("reason", "")
            
            # Format: emoji based on relationship type
            type_emoji = {
                "概念重叠": "🔄",
                "因果链条": "⛓️",
                "互补视角": "🔀",
                "对立观点": "⚔️"
            }.get(link_type, "🔗")
            
            entry = f"- {type_emoji} **{link_type}** → [[{target_file}]]：{reason}"
            new_entries.append(entry)
        
        if not new_entries:
            return False
        
        # Find the 🔗 section and append links
        link_block = "\n".join(new_entries)
        
        # Try to find the Connections section
        connections_pattern = r'(##\s*🔗.*?\n)(.*?)(\n##|\Z)'
        match = re.search(connections_pattern, content, re.DOTALL)
        
        if match:
            # Append to existing section
            section_header = match.group(1)
            section_body = match.group(2).rstrip()
            section_end = match.group(3)
            
            # Add a separator if there's already content
            if section_body.strip():
                updated_section = f"{section_header}{section_body}\n\n### 🌐 AI 自动发现的关联\n{link_block}{section_end}"
            else:
                updated_section = f"{section_header}\n### 🌐 AI 自动发现的关联\n{link_block}{section_end}"
            
            content = content[:match.start()] + updated_section + content[match.end():]
        else:
            # No connections section found, append at end
            content += f"\n\n## 🔗 盲区与关联反思 (Connections)\n\n### 🌐 AI 自动发现的关联\n{link_block}\n"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        
        logger.info(f"  🔗 Inserted {len(new_entries)} links into {os.path.basename(filepath)}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to insert links into {filepath}: {e}")
        return False


def process_auto_linking():
    """
    Main entry point: scan skill library, discover relationships, insert [[双链]].
    """
    logger.info("🌐 Starting Auto-Linker: Knowledge Graph weaving...")
    
    if not os.path.exists(SKILLS_DIR):
        logger.warning(f"Skills directory not found: {SKILLS_DIR}")
        return
    
    # Get all valid .md files (exclude archived/merged)
    all_files = [
        f for f in os.listdir(SKILLS_DIR) 
        if f.endswith('.md') and not f.startswith('[已合并]')
    ]
    logger.info(f"Found {len(all_files)} active skill files.")
    
    if len(all_files) < 2:
        logger.info("Not enough files for linking. Skipping.")
        return
    
    # Extract summaries from all cards
    cards = []
    for fname in all_files:
        fpath = os.path.join(SKILLS_DIR, fname)
        summary = extract_card_summary(fpath)
        if summary:
            cards.append(summary)
    
    logger.info(f"Successfully extracted {len(cards)} card summaries.")
    
    # Build title lookup
    all_titles = {card["filename"]: card["title"] for card in cards}
    
    # Process in batches to stay within token limits
    all_links = []
    for i in range(0, len(cards), BATCH_SIZE):
        batch = cards[i:i + BATCH_SIZE]
        logger.info(f"Analyzing batch {i // BATCH_SIZE + 1} ({len(batch)} cards)...")
        
        batch_links = find_relationships_with_gemini(batch)
        all_links.extend(batch_links)
        logger.info(f"  Found {len(batch_links)} relationships in this batch.")
        
        # Rate limit between batches
        if i + BATCH_SIZE < len(cards):
            time.sleep(5)
    
    if not all_links:
        logger.info("No new relationships discovered.")
        return
    
    logger.info(f"🔍 Total relationships discovered: {len(all_links)}")
    
    # Group links by source file
    links_by_source: dict[str, list] = {}
    for link in all_links:
        source = link.get("source", "")
        if source not in links_by_source:
            links_by_source[source] = []
        links_by_source[source].append(link)
        
        # Also add reverse link (bidirectional)
        target = link.get("target", "")
        reverse_link = {
            "target": source,
            "type": link.get("type", "关联"),
            "reason": link.get("reason", "")
        }
        if target not in links_by_source:
            links_by_source[target] = []
        links_by_source[target].append(reverse_link)
    
    # Insert links into each card
    updated_count = 0
    for source_file, links in links_by_source.items():
        filepath = os.path.join(SKILLS_DIR, source_file)
        if not os.path.exists(filepath):
            continue
        
        if insert_links_into_card(filepath, links, all_titles):
            updated_count += 1
    
    logger.info(f"\n🎉 Auto-Linker complete! Updated {updated_count} cards with [[双链]] connections.")
    logger.info("💡 Open Obsidian Graph View to see your knowledge constellation!")
