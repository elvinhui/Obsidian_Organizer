"""
Skill Merger Module
Scans the skill library, detects similar skills by title similarity,
and uses Gemini AI to merge them into a single consolidated knowledge card.
"""

import os
import re
import json
import time
import logging
from datetime import datetime
from difflib import SequenceMatcher
from itertools import combinations
from google import genai
from google.genai import types
from config import SKILLS_DIR, GEMINI_API_KEY, ARCHIVES_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

# Similarity threshold (0.0 to 1.0). Titles above this are considered "similar".
SIMILARITY_THRESHOLD = 0.45


def normalize_title(filename: str) -> str:
    """Strip prefixes (💡, emoji), file extension, and common noise from a filename."""
    name = os.path.splitext(filename)[0]
    # Remove leading emoji / special chars
    name = re.sub(r'^[💡🛠️💼💰🤔⭐\s]+', '', name)
    return name.strip()


def extract_core_content(filepath: str) -> str:
    """Extracts the core concept from a skill card for similarity matching."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        core_match = re.search(r'##\s*💡.*?\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        return core_match.group(1).strip()[:300] if core_match else content[:300]
    except Exception:
        return ""

def content_similarity(a: str, b: str) -> float:
    """Compute fuzzy similarity between two content strings."""
    return SequenceMatcher(None, a, b).ratio()

def find_similar_groups(filenames: list[str]) -> list[list[str]]:
    """
    Groups filenames by content similarity.
    Returns a list of groups, where each group contains >= 2 similar filenames.
    """
    contents = {f: extract_core_content(os.path.join(SKILLS_DIR, f)) for f in filenames}
    
    # Build an adjacency map of similar files
    adjacency: dict[str, set[str]] = {f: set() for f in filenames}
    
    for f1, f2 in combinations(filenames, 2):
        if not contents[f1] or not contents[f2]:
            continue
        sim = content_similarity(contents[f1], contents[f2])
        if sim >= SIMILARITY_THRESHOLD:
            adjacency[f1].add(f2)
            adjacency[f2].add(f1)
    
    # BFS / Union-Find to build connected groups
    visited = set()
    groups = []
    
    for f in filenames:
        if f in visited or not adjacency[f]:
            continue
        # BFS to find full group
        group = []
        queue = [f]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            group.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(group) >= 2:
            groups.append(sorted(group))
    
    return groups


def merge_skills_with_gemini(file_contents: dict[str, str]) -> dict:
    """
    Uses Gemini to merge multiple similar skill files into one consolidated knowledge card.
    
    Args:
        file_contents: dict mapping filename -> markdown content
    
    Returns:
        dict with 'title' and 'content' keys for the merged skill.
    """
    files_text = ""
    for fname, content in file_contents.items():
        files_text += f"\n{'='*60}\n📄 文件名: {fname}\n{'='*60}\n{content}\n"
    
    prompt = f"""你是一位专业的知识管理专家。以下是多个来自同一主题的知识卡片（Obsidian Markdown 文件），它们内容高度相似或互补。

请你将它们**合并成一份终极版本的知识卡片**，要求：

1. **去重**：删除所有重复的观点和内容
2. **取精**：保留每个文件中最精华、最独到的洞见
3. **补全**：如果不同文件有互补的观点，全部整合
4. **结构化**：使用以下 Markdown 模板格式输出

输出格式（严格遵守）：
```
---
创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
知识分类: [从内容中判断，如 财商知识/认知提升/AI技术]
掌握状态: ⏳ 待复习 (需要安排时间重温)
标签: [相关标签，必须用逗号分隔且不能包含井号，如: 投资, 心理学]
---
# [为合并后的知识起一个精炼的标题]

## 🧠 核心认知 (Core Concepts)
[整合所有文件中最核心的概念，去重后列出]

## ⚡ 行动指南 / SOP (Action Steps)
[整合所有文件中的行动步骤，去重、排序]

## 🔗 思维连接 (Connections)
[整合所有文件中的关联思考，去重]
```

以 JSON 格式返回，包含两个字段：
- "title": 合并后的标题（简短精炼，用于文件名）
- "content": 完整的 Markdown 内容

待合并的文件内容：
{files_text}
"""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.1-pro',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            result = json.loads(response.text)
            return result
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED"]):
                delay = (2 ** attempt) * 15
                logger.warning(f"Gemini rate limit. Retrying in {delay}s (Attempt {attempt+1}). Error: {err_str}")
                time.sleep(delay)
            else:
                logger.error(f"Gemini merge failed: {e}")
                raise
    
    raise Exception("Max retries exceeded for Gemini merge call.")


def process_skill_merging():
    """
    Main entry point: scan skill library, find similar groups, merge with Gemini.
    """
    logger.info("🔄 Starting skill similarity scan...")
    
    if not os.path.exists(SKILLS_DIR):
        logger.warning(f"Skills directory not found: {SKILLS_DIR}")
        return
    
    # Get all valid .md files (exclude archived/merged)
    all_files = [
        f for f in os.listdir(SKILLS_DIR) 
        if f.endswith('.md') and not f.startswith('[已合并]')
    ]
    logger.info(f"Found {len(all_files)} skill files.")
    
    if len(all_files) < 2:
        logger.info("Not enough files to compare. Skipping.")
        return
    
    # Find similar groups
    groups = find_similar_groups(all_files)
    
    if not groups:
        logger.info("✅ No similar skills detected. Library is clean!")
        return
    
    logger.info(f"🔍 Found {len(groups)} groups of similar skills to merge.")
    
    merged_count = 0
    for i, group in enumerate(groups):
        logger.info(f"\n--- Group {i+1}: {len(group)} files ---")
        for f in group:
            logger.info(f"  📄 {f}")
        
        # Read all file contents
        file_contents = {}
        for fname in group:
            fpath = os.path.join(SKILLS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    file_contents[fname] = f.read()
            except Exception as e:
                logger.error(f"Failed to read {fname}: {e}")
        
        if len(file_contents) < 2:
            continue
        
        # Merge with Gemini
        try:
            merged = merge_skills_with_gemini(file_contents)
            
            # Gemini sometimes returns a list instead of a single dict
            if isinstance(merged, list) and len(merged) > 0:
                merged = merged[0]
                
            merged_title = merged.get("title", f"合并技能_{i+1}")
            merged_content = merged.get("content", "")
            
            if not merged_content:
                logger.warning(f"Gemini returned empty content for group {i+1}. Skipping.")
                continue
            
            # Save merged file
            safe_title = re.sub(r'[\\/:*?"<>|]', '-', merged_title)
            merged_path = os.path.join(SKILLS_DIR, f"{safe_title}.md")
            
            # Avoid overwriting if same name already exists
            if os.path.exists(merged_path):
                merged_path = os.path.join(SKILLS_DIR, f"{safe_title}_合并版.md")
            
            with open(merged_path, "w", encoding="utf-8") as f:
                f.write(merged_content)
                f.flush()
                os.fsync(f.fileno())
            logger.info(f"✅ Merged file saved and synced: {os.path.basename(merged_path)}")
            
            # Archive originals by moving them to ARCHIVES_DIR
            import shutil
            os.makedirs(ARCHIVES_DIR, exist_ok=True)
            for fname in group:
                old_path = os.path.join(SKILLS_DIR, fname)
                new_path = os.path.join(ARCHIVES_DIR, fname)
                try:
                    shutil.move(old_path, new_path)
                    logger.info(f"  📦 Archived: {fname} → {ARCHIVES_DIR}")
                except Exception as e:
                    logger.error(f"  Failed to archive {fname}: {e}")
            
            merged_count += 1
            
            # Rate limit between groups
            if i < len(groups) - 1:
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Failed to merge group {i+1}: {e}")
            continue
    
    logger.info(f"\n🎉 Skill merging complete! Merged {merged_count} groups.")
