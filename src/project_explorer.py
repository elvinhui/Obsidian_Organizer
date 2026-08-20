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

    prompt = f"""你现在是顶尖的 Python 自动化架构师团队。

请阅读我 Obsidian 知识库中现有的全部内容（技能卡片 + 灵感碎片）。
综合这些信息，挖掘出我潜意识中真正需要的、能极大提升我生产力的自动化需求，并构思出 3-5 个**高度定制化的 Python 自动化项目**。

要求：
对于每一个构思的项目，你必须运用“规格驱动开发 (SDD)”的方法论，进行极客风格的详尽分析。
每个项目都必须包含以下结构：

1. 🎯 **项目名称与核心目标**：必须切中我的痛点（如：结合 Python + Gemini API + Obsidian）。
2. 🔍 **四路调研 (4-Path Research)**：
   - 数据源：依赖什么输入？API限制如何？
   - 开源实现：Github是否有现成轮子？
   - 可行性：最大的技术卡点在哪？
3. ⚖️ **法庭式对抗选型 (Tech Court)**：
   - 🔴 **红队挑刺**：指出最容易崩溃、成本最高的技术点。
   - 🔵 **蓝队辩护**：提出轻量级 MVP 替代方案。
   - 👨‍⚖️ **法官拍板**：宣判最终必须采用的技术栈。
4. 🛣️ **SDD 路线图**：列出分阶段任务列表 (Checkbox)，并强制包含自动化测试 (pytest) 环节。

说明：
- 语言风格极客、犀利、拒绝废话。
- 采用全 Markdown 格式。每个项目用 `##` 标题隔开。

我的知识库内容如下：
{resources_text}
"""

    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash',
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
        f.flush()
        os.fsync(f.fileno())

    logger.info(f"✅ Project ideas saved and synced: {filepath}")
    return filepath
