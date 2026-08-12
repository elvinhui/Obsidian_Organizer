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
    prompt = f"""你是一位资深的项目经理和系统架构师。
用户在“灵感库”中记录了一个灵感，请你根据它的【灵感分类】，将这个原始的、粗糙的灵感转化为一个结构化的、可落地的项目计划。

【灵感标题】：{idea['title']}
【灵感分类】：{idea['category']}
【原始记录】：
{idea['content']}

请输出一份 Markdown 格式的项目计划书，必须包含以下结构：
1. **🎯 项目目标 (Project Goal)**：清晰定义项目的最终交付物和预期价值。
2. **🛠️ 技术方案与选型 (Tech Stack)**：如果是自动化/编程项目，建议具体的语言、库或工具；如果是非技术项目，列出所需的资源和方法论。
3. **🗺️ 阶段执行计划 (Roadmap)**：将项目拆解为 3-4 个可执行的阶段，每个阶段列出具体的任务清单（Checkbox）。
4. **⚠️ 潜在风险与应对策 (Risk Mitigation)**：分析项目中可能遇到的阻力并给出预案。

输出要求：
- 语气专业、务实。
- 完全以 Markdown 格式输出，不要多余的寒暄。
- 内容必须紧扣用户的【灵感分类】（例如分类为“自动化构想”，则方案必须偏向自动化开发）。
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
