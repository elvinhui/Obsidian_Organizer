import os
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def scan_inbox(inbox_dir: str) -> List[Dict[str, Any]]:
    """
    Scans the inbox directory for pending tasks.
    Returns a list of tasks.
    """
    tasks = []
    
    # Check if inbox directory exists
    if not os.path.exists(inbox_dir):
        logger.warning(f"Inbox directory not found: {inbox_dir}")
        return tasks

    # Regex to match: - [ ] #待处理 2026-07-26 23:40 | https://...
    task_pattern = re.compile(r"^(\s*-\s+\[ \]\s+#待处理)\s+(.*?)\s*\|\s*(.*)$")

    for filename in os.listdir(inbox_dir):
        if filename.endswith(".md"):
            file_path = os.path.join(inbox_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                for i, line in enumerate(lines):
                    match = task_pattern.match(line)
                    if match:
                        tasks.append({
                            "file_path": file_path,
                            "line_number": i,
                            "original_line": line,
                            "date_time_str": match.group(2).strip(),
                            "payload": match.group(3).strip(),
                            "prefix": match.group(1) # The "- [ ] #待处理" part
                        })
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {e}")

    return tasks

def mark_task_completed(file_path: str, original_line: str) -> bool:
    """
    Safely replaces the '- [ ]' with '- [x]' and '#待处理' with '#已处理' 
    for the specific line to avoid corrupting the file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # We replace the exact line we found, ignoring trailing whitespaces/newlines
        found = False
        original_clean = original_line.strip()
        for i, line in enumerate(lines):
            if line.strip() == original_clean:
                # Replace the state
                new_line = line.replace("- [ ]", "- [x]", 1).replace("#待处理", "#已处理", 1)
                lines[i] = new_line
                found = True
                break
        
        if not found:
            logger.warning(f"Could not find original line in {file_path} to mark as completed.")
            return False

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
            
        logger.info(f"Marked task as completed in {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to mark task as completed in {file_path}: {e}")
        return False
