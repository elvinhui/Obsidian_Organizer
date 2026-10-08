import os
import pytest
from src.template_engine import render_and_save
from src.project_explorer import scan_existing_resources

def test_template_engine_routes_idea_to_ideas_dir(tmp_path, monkeypatch):
    ideas_dir = tmp_path / "01_Ideas"
    skills_dir = tmp_path / "05_Skills"
    ideas_dir.mkdir()
    skills_dir.mkdir()
    
    import src.template_engine
    monkeypatch.setattr(src.template_engine, "IDEAS_DIR", str(ideas_dir))
    monkeypatch.setattr(src.template_engine, "SKILLS_DIR", str(skills_dir))
    
    idea_data = {
        "category": "自动化构想",
        "title": "Obsidian智能灵感挖掘机",
        "tags": ["#Python", "#自动化"],
        "core_concepts": "自动从灵感库中提炼高价值项目。",
        "action_sop": "先写一个扫描脚本验证逻辑。",
        "connections": "- 提高灵感转化率。"
    }
    
    saved_path = render_and_save(idea_data)
    assert os.path.exists(saved_path)
    assert str(ideas_dir) in saved_path
    assert os.path.basename(saved_path).startswith("💡 ")
    
    with open(saved_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "灵感分类: 自动化构想" in content
    assert "## 💭 这是个什么点子？(The Idea)" in content

def test_project_explorer_scans_ideas_dir(tmp_path, monkeypatch):
    ideas_dir = tmp_path / "01_Ideas"
    skills_dir = tmp_path / "05_Skills"
    inbox_dir = tmp_path / "00_Inbox"
    ideas_dir.mkdir()
    skills_dir.mkdir()
    inbox_dir.mkdir()
    
    sample_idea = ideas_dir / "💡 智能书签同步器.md"
    sample_idea.write_text("# 智能书签同步器\n一键将浏览器书签同步至知识库。", encoding="utf-8")
    
    import src.project_explorer
    monkeypatch.setattr(src.project_explorer, "IDEAS_DIR", str(ideas_dir))
    monkeypatch.setattr(src.project_explorer, "SKILLS_DIR", str(skills_dir))
    monkeypatch.setattr(src.project_explorer, "INBOX_DIR", str(inbox_dir))
    
    resources = scan_existing_resources()
    assert "### 💡 核心灵感卡片: 💡 智能书签同步器.md" in resources
    assert "一键将浏览器书签同步至知识库" in resources
