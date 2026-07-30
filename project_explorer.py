import os
import json
import logging
from datetime import datetime
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, SKILLS_DIR, PROJECTS_DIR, INBOX_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)


def scan_existing_resources() -> str:
    """Scans skill cards and inbox files to build a summary of all existing resources."""
    resources = []

    # 1. Read all skill cards
    if os.path.isdir(SKILLS_DIR):
        for filename in os.listdir(SKILLS_DIR):
            if filename.endswith(".md"):
                filepath = os.path.join(SKILLS_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    resources.append(f"### 技能卡片: {filename}\n{content}\n")
                except Exception as e:
                    logger.warning(f"Could not read {filepath}: {e}")

    # 2. Read inbox topics (just the filenames tell us the categories)
    if os.path.isdir(INBOX_DIR):
        for filename in os.listdir(INBOX_DIR):
            if filename.endswith(".md"):
                filepath = os.path.join(INBOX_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    resources.append(f"### 收件箱主题: {filename}\n{content}\n")
                except Exception as e:
                    logger.warning(f"Could not read {filepath}: {e}")

    return "\n---\n".join(resources)


def generate_project_ideas(resources_text: str) -> str:
    """Sends all resources to Gemini and asks for Python automation project ideas."""
    import time

    prompt = f"""你是一位资深的 Python 自动化架构师和个人效率专家。

以下是用户 Obsidian 知识库中的所有现有资源（技能卡片 + 收件箱主题）。
请基于这些资源，深度分析用户的兴趣领域、知识结构和痛点，然后提出 5-8 个**可用 Python 实现的自动化项目**。

要求：
1. 每个项目必须与用户现有的知识/兴趣**高度相关**
2. 优先推荐能复用现有技术栈的项目（Python + Gemini API + yt-dlp + Obsidian）
3. 项目从简单到复杂排列
4. 每个项目包含：项目名称、痛点分析、技术方案、所需库、预计工期、难度星级
5. 输出格式为 Markdown，使用中文
6. 在末尾添加一个优先级矩阵表格

用户现有资源：
{resources_text}
"""

    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7
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
        raise Exception("Max retries exceeded for project exploration.")

    return response.text


def explore_and_save():
    """Main entry point: scan resources, generate ideas, save to Projects folder."""
    # Build filename first to check if we already explored today
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"Python自动化项目探索_{date_str}.md"
    filepath = os.path.join(PROJECTS_DIR, filename)

    if os.path.exists(filepath):
        logger.info(f"⏭️ Project exploration already completed today ({filename}). Skipping to save quota.")
        return None

    logger.info("🔍 Scanning existing vault resources for project exploration...")
    resources_text = scan_existing_resources()

    if not resources_text.strip():
        logger.warning("No resources found in vault. Skipping project exploration.")
        return None

    logger.info(f"📚 Found {resources_text.count('###')} resource sections. Sending to Gemini...")
    raw_ideas = generate_project_ideas(resources_text)

    # Build the final markdown
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"""---
创建时间: {now}
状态: 🌱 探索中
标签: #Python自动化 #Gemini #项目探索 #AI生成
来源: AI Brain Engine 自动探索
---
"""
    full_content = header + raw_ideas

    # Save to Projects folder
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"Python自动化项目探索_{date_str}.md"
    filepath = os.path.join(PROJECTS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)

    logger.info(f"✅ Project ideas saved to {filepath}")
    return filepath
