import os
import re
import logging
from datetime import datetime
from config import OBSIDIAN_BASE_PATH, PROJECTS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def is_fat_note(filepath: str, content: str) -> dict:
    """Analyze a markdown file to determine its 'fatness' (Information Obesity)."""
    # 1. Count Links
    wikilinks = re.findall(r'\[\[(.*?)\]\]', content)
    link_count = len(wikilinks)
    unique_links = len(set([link.split('|')[0] for link in wikilinks])) # Ignore aliases for uniqueness
    
    # 2. Count approximate "words" (using length of text as a proxy for Chinese/English mix)
    text_length = len(content.replace('\n', '').replace(' ', ''))
    if text_length < 50: # Skip very short notes
        return None
        
    # 3. Calculate Density (Links per 100 characters)
    link_density = (link_count / text_length) * 100
    
    # 4. Check for Actionability (Code blocks or checkboxes)
    has_code = bool(re.search(r'```(?:python|bash|javascript|js|ts|go|rust|cpp)', content))
    has_todos = bool(re.search(r'- \[[ x]\]', content))
    is_actionable = has_code or has_todos
    
    # Base heuristic for "Fat Note":
    # More than 10 links AND density > 3 (3 links per 100 chars) AND not actionable
    # Or just exceptionally high links (>20)
    score = (link_count * 0.5) + (link_density * 2)
    if not is_actionable:
        score *= 1.5 # Penalty for lacking action
        
    return {
        'filename': os.path.basename(filepath),
        'filepath': filepath,
        'link_count': link_count,
        'unique_links': unique_links,
        'link_density': round(link_density, 2),
        'is_actionable': is_actionable,
        'score': round(score, 2)
    }

def scan_vault_for_fat_notes():
    logger.info("🔍 Scanning vault for 'Fat Notes' (Information Obesity)...")
    
    fat_notes = []
    
    for root, dirs, files in os.walk(OBSIDIAN_BASE_PATH):
        # Exclude hidden folders, templates, etc.
        dirs[:] = [d for d in dirs if not d.startswith('.') and 'Template' not in d and 'Sandboxes' not in d]
        
        for file in files:
            if not file.endswith('.md'):
                continue
                
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                analysis = is_fat_note(filepath, content)
                if analysis and analysis['score'] > 15: # Arbitrary threshold for "fatness"
                    fat_notes.append(analysis)
            except Exception as e:
                logger.debug(f"Could not read {filepath}: {e}")
                
    # Sort by score descending
    fat_notes.sort(key=lambda x: x['score'], reverse=True)
    return fat_notes[:30] # Top 30 offenders

def generate_report():
    fat_notes = scan_vault_for_fat_notes()
    
    if not fat_notes:
        logger.info("✅ No fat notes found! Your vault is highly actionable.")
        return
        
    date_str = datetime.now().strftime("%Y%m%d")
    report_filename = f"💣虚胖笔记扫雷报告_{date_str}.md"
    
    # Save it to 03 资产库_Areas or a similar root-level folder. We'll use 02 项目库_Projects for now
    report_path = os.path.join(PROJECTS_DIR, report_filename)
    
    lines = [
        "---",
        f"创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "标签: #系统报告 #虚胖扫雷 #数字断舍离",
        "---",
        "# 💣 虚胖笔记扫雷报告 (Information Obesity Report)\n",
        "> **数字生命体 LAAP 提示**：限制‘信息肥胖’，停止撰写高密度的元理论桥接笔记，实行‘1:1输出杠杆率’！\n",
        "以下是您的知识库中，**链接密度极高且缺乏具体执行代码/待办**的“元理论虚胖笔记”。\n",
        "**🎯 您的下一步行动**：",
        "1. **审视**：打开这些笔记，问自己“这能转化为什么自动化脚本或决策模型？”",
        "2. **斩断**：直接删掉无意义的过度双向链接。",
        "3. **杠杆**：将核心观点丢进 `01 想法库_Ideas`，打上 `#SDD_Pending` 标签，让 Agent 给您把理论变成代码！\n",
        "## 🏆 “最虚胖”笔记排行榜 (Top 30)\n",
        "| 排名 | 笔记名称 | 肥胖指数 | 总链接数 | 密度(链/百字) | 缺乏行动力 | 建议 |",
        "|---|---|---|---|---|---|---|"
    ]
    
    for i, note in enumerate(fat_notes, 1):
        filename_no_ext = note['filename'].replace('.md', '')
        action_status = "🔴 是" if not note['is_actionable'] else "🟢 否"
        
        lines.append(
            f"| {i} | [[{filename_no_ext}]] | **{note['score']}** | {note['link_count']} | {note['link_density']} | {action_status} | 建议重构为SDD或删除 |"
        )
        
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
        
    logger.info(f"✅ Fat note report generated: {report_path}")
    
if __name__ == "__main__":
    generate_report()
