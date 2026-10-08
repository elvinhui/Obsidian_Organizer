import os
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def scan_inbox_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Scans a single inbox markdown file for pending tasks.
    Supports standard format:
        - [ ] #待处理 2026-07-26 23:40 | https://...
    And also unformatted pending checkboxes with URLs:
        - [ ] https://...
    """
    tasks = []
    if not os.path.exists(file_path) or not file_path.endswith(".md"):
        return tasks
        
    task_pattern = re.compile(r"^(\s*-\s+\[ \]\s+#待处理)\s+(.*?)\s*\|\s*(.*)$")
    url_pattern = re.compile(r"(https?://[^\s\>\]\)]+)")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines):
            clean_l = line.strip()
            if "#已处理" in clean_l or "#Failed" in clean_l or clean_l.startswith("- [x]"):
                continue
                
            match = task_pattern.match(line)
            if match:
                tasks.append({
                    "file_path": file_path,
                    "line_number": i,
                    "original_line": line,
                    "date_time_str": match.group(2).strip(),
                    "payload": match.group(3).strip(),
                    "prefix": match.group(1)
                })
            elif clean_l.startswith("- [ ]"):
                url_match = url_pattern.search(line)
                if url_match:
                    tasks.append({
                        "file_path": file_path,
                        "line_number": i,
                        "original_line": line,
                        "date_time_str": "",
                        "payload": url_match.group(1).strip(),
                        "prefix": "- [ ]"
                    })
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        
    return tasks

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

    for filename in os.listdir(inbox_dir):
        if filename.endswith(".md"):
            file_path = os.path.join(inbox_dir, filename)
            tasks.extend(scan_inbox_file(file_path))

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
                if "#待处理" in line:
                    new_line = line.replace("- [ ]", "- [x]", 1).replace("#待处理", "#已处理", 1)
                else:
                    new_line = line.replace("- [ ]", "- [x]", 1)
                    if "#已处理" not in new_line:
                        new_line = new_line.rstrip('\r\n') + " #已处理\n"
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

def mark_task_failed(file_path: str, original_line: str, tag: str = "#Failed") -> bool:
    """
    Marks a task line with a failure tag (e.g. #Failed) so subsequent cycles skip it.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        found = False
        original_clean = original_line.strip()
        for i, line in enumerate(lines):
            if line.strip() == original_clean:
                if "#待处理" in line:
                    new_line = line.replace("#待处理", tag, 1)
                elif tag not in line:
                    new_line = line.rstrip('\r\n') + f" {tag}\n"
                else:
                    new_line = line
                lines[i] = new_line
                found = True
                break
        if not found:
            logger.warning(f"Could not find original line in {file_path} to mark as failed.")
            return False
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        logger.info(f"Marked task as {tag} in {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to mark task as failed in {file_path}: {e}")
        return False

