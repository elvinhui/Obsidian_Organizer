import os
import json
import logging
from datetime import datetime
from google import genai
from google.genai import types
try:
    from config import GEMINI_API_KEY, SKILLS_DIR, PROJECTS_DIR, INBOX_DIR, IDEAS_DIR
except ImportError:
    from src.config import GEMINI_API_KEY, SKILLS_DIR, PROJECTS_DIR, INBOX_DIR, IDEAS_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)


def scan_existing_resources() -> str:
    """Scans ideas library (primary anchor), skill cards, and inbox files to build a summary of all existing resources."""
    resources = []

    # 1. Read all idea cards from Ideas Library (PRIMARY ANCHOR)
    if os.path.isdir(IDEAS_DIR):
        for filename in os.listdir(IDEAS_DIR):
            if filename.endswith(".md"):
                filepath = os.path.join(IDEAS_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    resources.append(f"### 💡 核心灵感卡片: {filename}\n{content}\n")
                except Exception as e:
                    logger.warning(f"Could not read {filepath}: {e}")

    # 2. Read all skill cards (Technical capability & cognitive foundation)
    if os.path.isdir(SKILLS_DIR):
        for filename in os.listdir(SKILLS_DIR):
            if filename.endswith(".md"):
                filepath = os.path.join(SKILLS_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    resources.append(f"### 🛠️ 现有技能与认知卡片: {filename}\n{content}\n")
                except Exception as e:
                    logger.warning(f"Could not read {filepath}: {e}")

    # 3. Read inbox topics (just the filenames tell us the categories)
    if os.path.isdir(INBOX_DIR):
        for filename in os.listdir(INBOX_DIR):
            if filename.endswith(".md"):
                filepath = os.path.join(INBOX_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    resources.append(f"### 📥 收件箱主题: {filename}\n{content}\n")
                except Exception as e:
                    logger.warning(f"Could not read {filepath}: {e}")

    return "\n---\n".join(resources)


def generate_project_ideas(resources_text: str) -> str:
    """Sends all resources to Gemini and asks for Python automation project ideas based on the ideas library."""
    import time

    prompt = f"""你现在是顶尖的 Python 自动化架构师团队。

【核心任务】：
请仔细阅读我 Obsidian 知识库中的现有资源。
**特别关键要求**：你必须以【💡 核心灵感卡片 (01 灵感库_Ideas)】中的真实痛点、点子和构想作为【核心锚点与第一需求输入】！
同时结合【🛠️ 现有技能与认知卡片 (05 技能库)】中沉淀的技术方案、认知模型与工具链（如 Python + Gemini API + yt-dlp + Obsidian + SQLite），
针对灵感库中的痛点进行深度升维与技术落地，构思出 3-5 个**基于灵感库深度提炼的 Python 自动化/实战项目**。

要求：
对于每一个构思的项目，你必须运用“规格驱动开发 (SDD)”的方法论，进行极客风格的详尽分析。
每个项目都必须明确注明它源自或延伸自灵感库中的哪张卡片（例如：`关联灵感：[[💡 抖音关注列表清理助手]]`）。
每个项目都必须包含以下结构：

1. 🎯 **项目名称与核心目标**：明确指出解决了灵感库中的什么痛点与需求。
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
    candidate_models = ["gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.5-flash"]
    
    for curr_model in candidate_models:
        for attempt in range(max_retries):
            try:
                logger.info(f"Generating project ideas with model {curr_model} (attempt {attempt + 1})...")
                response = client.models.generate_content(
                    model=curr_model,
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
                    logger.warning(f"Gemini API limit hit for {curr_model}. Retrying in {delay}s (Attempt {attempt+1}/{max_retries}): {err_str}")
                    time.sleep(delay)
                else:
                    logger.warning(f"Error calling {curr_model}: {e}, trying fallback model...")
                    break
        if response:
            break

    if not response:
        raise Exception("Max retries exceeded for project exploration.")

    return response.text


def explore_and_save(force: bool = False):
    """Main entry point: scan resources, generate ideas, save to Projects folder."""
    # Build filename first to check if we already explored today
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"Python自动化项目探索_{date_str}.md"
    filepath = os.path.join(PROJECTS_DIR, filename)

    if os.path.exists(filepath) and not force:
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
