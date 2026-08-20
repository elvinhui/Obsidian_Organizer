import os
import re
import logging
import time
from datetime import datetime
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, IDEAS_DIR, PROJECTS_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

def get_pending_ideas() -> list[dict]:
    """Scans the ideas directory for markdown files that haven't been converted to projects yet."""
    ideas = []
    
    if not os.path.isdir(IDEAS_DIR):
        logger.warning(f"Ideas directory not found: {IDEAS_DIR}")
        return ideas

    for filename in os.listdir(IDEAS_DIR):
        if not filename.endswith(".md"):
            continue
            
        filepath = os.path.join(IDEAS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Skip if already converted
            if "已转项目" in content or "状态: 已转换" in content:
                continue
                
            # Extract category (e.g. 灵感分类: 自动化构想)
            category_match = re.search(r"灵感分类:\s*(.+)", content)
            category = category_match.group(1).strip() if category_match else "未分类"
            
            # Extract title (either from h1 or filename)
            title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else filename.replace(".md", "").replace("💡", "").strip()
            
            ideas.append({
                "filepath": filepath,
                "filename": filename,
                "title": title,
                "category": category,
                "content": content
            })
        except Exception as e:
            logger.error(f"Failed to read idea file {filepath}: {e}")
            
    return ideas

def generate_project_plan(idea: dict) -> str:
    """Uses Gemini to turn an idea into an actionable project plan."""
    prompt = f"""你现在是顶尖的架构师团队，正在执行“规格驱动开发 (SDD)”。
你需要把以下原始灵感，升级为一份极具深度的“法庭式技术选型与规格说明书 (Spec)”。

【原始灵感】
所属分类：{idea['category']}
灵感标题：{idea['title']}
灵感详情：
{idea['content']}

请你启动**四路并行调研**（产品形态、数据源、开源实现、可行性），并引入**“法庭式对抗模块”**（红队挑刺、蓝队辩护、法官拍板）。
必须输出为纯 Markdown 格式，包含以下结构：

1. **🚀 1. 核心产品形态 (Product Form)**：一句话定义它是什么，解决什么痛点。
2. **🔍 2. 四路调研分析 (4-Path Research)**：
   - 数据源：依赖什么数据？API限制如何？
   - 开源实现：Github上是否有现成轮子（如LangChain, autogen等）？
   - 可行性：技术卡点在哪？
3. **⚖️ 3. 法庭式技术选型对抗 (Tech Selection Court)**：
   - 🔴 **红队 (Red Team)**：无情挑刺。指出原计划中最容易崩溃、成本最高、或者最不切实际的技术点。
   - 🔵 **蓝队 (Advocate)**：极力辩护。提出最轻量级、最优雅的替代方案或 MVP 方案。
   - 👨‍⚖️ **法官 (Judge AI)**：一锤定音。根据红蓝对抗，最终宣判**必须采用的技术栈 (Tech Stack)**。
4. **🛣️ 4. SDD 规格驱动开发路线 (Roadmap)**：
   - 列出 3-4 个阶段（Phase）。强制包含自动化测试（pytest）环节。必须以 Checkbox `- [ ]` 形式输出。

注意：
- 语言风格极其精炼，专业，直击要害（极客风）。
- 绝不要用大段废话，用列表和粗体突出重点。
- 最终产出必须能指导一个 Agent 直接写出 Python 代码骨架。
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
        raise Exception("Max retries exceeded for project plan generation.")

    return response.text

def mark_idea_as_converted(filepath: str, project_filename: str):
    """Adds a tag to the idea file so it won't be processed again."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Add a link to the project and a status tag
        if "---" in content:
            # Replace the first frontmatter block to insert the new status
            # Find the index of the first '---' and the second '---'
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                if "已转项目" not in frontmatter:
                    new_frontmatter = frontmatter + f"状态: 已转项目\n关联项目: [[{project_filename.replace('.md', '')}]]\n"
                    content = f"---{new_frontmatter}---{parts[2]}"
        else:
            content = f"状态: 已转项目\n关联项目: [[{project_filename.replace('.md', '')}]]\n\n" + content
            
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        logger.error(f"Failed to mark idea {filepath} as converted: {e}")

def process_ideas_to_projects():
    """Main entry point to convert pending ideas to projects."""
    logger.info("💡 Scanning Ideas library for unconverted items...")
    ideas = get_pending_ideas()
    
    if not ideas:
        logger.info("No pending ideas to convert.")
        return
        
    logger.info(f"🚀 Found {len(ideas)} idea(s) to convert into projects.")
    
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    
    for idea in ideas:
        logger.info(f"Generating project plan for idea: {idea['title']}...")
        try:
            project_plan_content = generate_project_plan(idea)
            
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            date_str = datetime.now().strftime("%Y%m%d")
            
            # Create a safe filename
            safe_title = re.sub(r'[\\/*?:"<>|]', "", idea['title'])
            project_filename = f"项目规划_{safe_title}_{date_str}.md"
            project_filepath = os.path.join(PROJECTS_DIR, project_filename)
            
            header = f"""---
创建时间: {now}
状态: 🏃 执行中
标签: #项目规划 #AI生成 #{idea['category'].replace(' ', '_')}
关联灵感: [[{idea['filename'].replace('.md', '')}]]
---
# 🚀 项目规划：{idea['title']}

"""
            full_content = header + project_plan_content
            
            with open(project_filepath, "w", encoding="utf-8") as f:
                f.write(full_content)
                f.flush()
                os.fsync(f.fileno())
                
            logger.info(f"✅ Saved and synced project plan: {project_filepath}")
            
            # Mark the original idea as converted
            mark_idea_as_converted(idea['filepath'], project_filename)
            
        except Exception as e:
            logger.error(f"Failed to convert idea '{idea['title']}' to project: {e}")
