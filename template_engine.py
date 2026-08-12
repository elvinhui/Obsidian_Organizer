import os
import re
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

from config import SKILLS_DIR

logger = logging.getLogger(__name__)

# Setup Jinja2 environment
TEMPLATE_DIR = os.path.join(os.path.dirname(__name__), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

def clean_filename(title: str) -> str:
    """Removes invalid characters for Windows filenames."""
    return re.sub(r'[\\/*?:"<>|]', "-", title)

def render_and_save(json_data: Dict[str, Any]) -> str:
    """
    Renders the appropriate Jinja2 template and saves it to the Skills Directory.
    Returns the file path of the saved file.
    """
    category = json_data.get("category", "")
    title = json_data.get("title", "Untitled Knowledge")
    
    # Determine which template to use based on the category
    idea_categories = ["自动化构想", "硬技能开发", "财富优化", "奇思妙想"]
    
    if category in idea_categories:
        template_name = "T_IdeaIncubator.md"
        status_or_feasibility = "⭐⭐ 中等 (需要查资料/花几天时间)"
        file_prefix = "💡 "
    else:
        template_name = "T_CoreKnowledge.md"
        status_or_feasibility = "⏳ 待复习 (需要安排时间重温)"
        file_prefix = ""

    template = env.get_template(template_name)
    
    # Prepare data for template
    creation_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    render_data = {
        "title": title,
        "creation_date": creation_date,
        "category": category,
        "status": status_or_feasibility,
        "tags": "[" + ", ".join(t.replace("#", "") for t in json_data.get("tags", [])) + "]",
        "core_concepts": json_data.get("core_concepts", ""),
        "action_sop": json_data.get("action_sop", ""),
        "connections": json_data.get("connections", "")
    }
    
    rendered_content = template.render(**render_data)
    
    # Ensure SKILLS_DIR exists
    os.makedirs(SKILLS_DIR, exist_ok=True)
    
    safe_title = clean_filename(title)
    filename = f"{file_prefix}{safe_title}.md"
    file_path = os.path.join(SKILLS_DIR, filename)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(rendered_content)
        f.flush()
        os.fsync(f.fileno())
        
    logger.info(f"✅ Saved and synced: {file_path}")
    return file_path
