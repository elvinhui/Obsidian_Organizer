import os
import re
import datetime
import logging
from typing import Optional, List, Dict, Any
import frontmatter
from .schema import MemoryRecord

logger = logging.getLogger(__name__)

DATE_REGEX = re.compile(r'(?:创建时间|日期|Date|date_created):\s*(\d{4}-\d{2}-\d{2})', re.IGNORECASE)
TAG_REGEX = re.compile(r'(?<!\S)#([\w\u4e00-\u9fa5\-_]+)')

def infer_category(file_path: str) -> str:
    """Infer note category from directory path."""
    normalized = file_path.replace("\\", "/")
    if "05 技能库" in normalized or "Skills" in normalized:
        return "skills"
    if "02 项目库" in normalized or "Projects" in normalized:
        return "projects"
    if "07 洞见库" in normalized or "Insights" in normalized:
        return "insights"
    if "03 资产库" in normalized or "Areas" in normalized:
        return "areas"
    if "01 灵感库" in normalized or "Ideas" in normalized:
        return "ideas"
    return "other"

def parse_date_string(date_val: Any) -> Optional[str]:
    """Defensively convert various date representations into YYYY-MM-DD string."""
    if not date_val:
        return None
    if isinstance(date_val, datetime.date):
        return date_val.strftime("%Y-%m-%d")
    if isinstance(date_val, datetime.datetime):
        return date_val.strftime("%Y-%m-%d")
    if isinstance(date_val, str):
        match = re.search(r'\d{4}-\d{2}-\d{2}', date_val)
        if match:
            return match.group(0)
    return None

def extract_tags(metadata: Dict[str, Any], content: str) -> List[str]:
    """Extract tags from both Frontmatter and Markdown body."""
    tag_set = set()
    
    # 1. Frontmatter tags
    raw_tags = metadata.get("tags") or metadata.get("tag") or metadata.get("标签")
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if t:
                clean_t = str(t).strip().lstrip("#")
                if clean_t:
                    tag_set.add(clean_t)
    elif isinstance(raw_tags, str):
        for t in re.split(r'[,;\s]+', raw_tags):
            clean_t = t.strip().lstrip("#")
            if clean_t:
                tag_set.add(clean_t)
                
    # 2. In-body tags
    for match in TAG_REGEX.finditer(content):
        t = match.group(1).strip()
        if t and not t.isdigit():  # Avoid matching plain numbers like #123
            tag_set.add(t)
            
    return sorted(list(tag_set))

def parse_markdown_file(file_path: str) -> Optional[MemoryRecord]:
    """
    Parse an Obsidian markdown file into a normalized MemoryRecord.
    Returns None if the file cannot be read or parsed.
    """
    if not os.path.exists(file_path) or not file_path.endswith('.md'):
        return None

    # Review checklists are transient task trackers, not permanent knowledge cards
    if os.path.basename(file_path).startswith("间隔复习_"):
        return None
        
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            post = frontmatter.load(f)
            
        metadata = dict(post.metadata) if post.metadata else {}
        content = post.content or ""
        
        # 1. Title and note_id
        file_basename = os.path.splitext(os.path.basename(file_path))[0]
        title = metadata.get('title') or file_basename
        note_id = str(metadata.get('id') or file_basename)
        category = infer_category(file_path)
        
        # 2. File modification time (system write time)
        try:
            mtime = os.path.getmtime(file_path)
            sys_write_time = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            sys_write_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        # 3. Bi-temporal inference for real_effect_time
        effect_date = None
        # Priority 1: explicit effective_date
        for key in ['effective_date', 'real_effect_time', '生效时间']:
            if key in metadata:
                effect_date = parse_date_string(metadata[key])
                if effect_date:
                    break
                    
        # Priority 2: creation date in metadata
        if not effect_date:
            for key in ['date_created', 'created_at', '创建时间', 'date']:
                if key in metadata:
                    effect_date = parse_date_string(metadata[key])
                    if effect_date:
                        break
                        
        # Priority 3: regex in content
        if not effect_date:
            match = DATE_REGEX.search(content[:500])
            if match:
                effect_date = match.group(1)
                
        # Priority 4: file ctime
        if not effect_date:
            try:
                ctime = os.path.getctime(file_path)
                effect_date = datetime.datetime.fromtimestamp(ctime).strftime("%Y-%m-%d")
            except Exception:
                pass
                
        # Fallback: today
        if not effect_date:
            effect_date = datetime.date.today().strftime("%Y-%m-%d")
            
        # 4. Expiration and supersession
        effective_until = parse_date_string(metadata.get('effective_until') or metadata.get('失效时间'))
        superseded_by = metadata.get('superseded_by') or metadata.get('被取代')
        if superseded_by:
            superseded_by = str(superseded_by).strip()
            
        # 5. SM-2 Spaced repetition fields
        try:
            sm2_ease = float(metadata.get('sm2_ease', 2.5))
        except (ValueError, TypeError):
            sm2_ease = 2.5
            
        try:
            sm2_interval = int(metadata.get('sm2_interval', 0))
        except (ValueError, TypeError):
            sm2_interval = 0
            
        sm2_next_review = parse_date_string(metadata.get('sm2_next_review'))
        # Only assign default sm2_next_review to reviewable categories (skills and insights)
        if not sm2_next_review and category in ['skills', 'insights']:
            # Default next review is 1 day after effective date or tomorrow
            try:
                base_dt = datetime.datetime.strptime(effect_date, "%Y-%m-%d").date()
                sm2_next_review = (base_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                sm2_next_review = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                
        # 6. Tags
        tags = extract_tags(metadata, content)
        
        # 7. Clean content text for indexing (strip raw YAML if any leaked)
        clean_content = content.strip()
        
        return MemoryRecord(
            note_id=note_id,
            file_path=os.path.normpath(file_path),
            title=title,
            category=category,
            frontmatter=metadata,
            content_text=clean_content,
            real_effect_time=effect_date,
            sys_write_time=sys_write_time,
            effective_until=effective_until,
            superseded_by=superseded_by,
            sm2_ease=sm2_ease,
            sm2_interval=sm2_interval,
            sm2_next_review=sm2_next_review,
            tags=tags,
            updated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    except Exception as e:
        logger.error(f"Error parsing markdown file {file_path}: {e}")
        return None
