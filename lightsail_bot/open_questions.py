import os
import random
import subprocess
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

def get_open_questions_dir(base_path: str) -> str:
    """Gets the path to the open questions directory on rclone."""
    return f"{base_path}/03 资产库_Areas/开放性思考"

def pick_random_unanswered_question(base_path: str) -> str:
    """
    Picks a random question that is still marked as '状态: 持续迭代'.
    Returns a tuple (filename, content_preview) or None if all are answered.
    """
    remote_dir = get_open_questions_dir(base_path)
    
    try:
        from telegram_bot import mount_path_to_remote
        rclone_remote_dir = mount_path_to_remote(remote_dir)
        
        # List all .md files
        lsf_result = subprocess.run(["rclone", "lsf", rclone_remote_dir], capture_output=True, text=True, timeout=15)
        if lsf_result.returncode != 0:
            logger.error(f"Failed to list open questions: {lsf_result.stderr}")
            return None
            
        files = [f.strip() for f in lsf_result.stdout.split('\n') if f.strip().endswith('.md')]
        unanswered_files = []
        
        # Read contents to check state
        for filename in files:
            cat_result = subprocess.run(["rclone", "cat", f"{rclone_remote_dir}/{filename}"], capture_output=True, text=True, timeout=15)
            if cat_result.returncode == 0:
                content = cat_result.stdout
                if "状态: 持续迭代" in content:
                    unanswered_files.append((filename, content))
                    
        if not unanswered_files:
            return None
            
        # Pick one randomly
        picked = random.choice(unanswered_files)
        
        # Extract prompt section from content
        filename, content = picked
        prompt_match = re.search(r'## ❓ 命题重述.*?>(.*?)(?:\n##|\Z)', content, re.DOTALL)
        if prompt_match:
            prompt_text = prompt_match.group(1).strip()
        else:
            prompt_text = content[:300] + "..."
            
        return {
            "filename": filename,
            "prompt": prompt_text,
            "full_content": content,
            "rclone_remote_dir": rclone_remote_dir
        }
    except Exception as e:
        logger.error(f"Error picking random question: {e}")
        return None

def save_answer(pick_data: dict, answer: str) -> bool:
    """
    Saves the user's answer to the file and updates its state to '已回答'.
    """
    try:
        filename = pick_data["filename"]
        content = pick_data["full_content"]
        rclone_remote_dir = pick_data["rclone_remote_dir"]
        
        # Update state
        content = content.replace("状态: 持续迭代", "状态: 已回答")
        
        # Ensure target section exists and append
        target_section = "## 🎯 核心破局点"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        answer_block = f"\n\n**[{timestamp}] 我的3句话破局**\n{answer}\n"
        
        if target_section in content:
            content = content.replace(target_section, target_section + answer_block)
        else:
            content += f"\n\n{target_section}{answer_block}"
            
        # Write back via rclone
        from telegram_bot import rclone_write_new
        filepath = f"{rclone_remote_dir}/{filename}"
        
        # Create temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write(content)
            temp_path = f.name
            
        # Copy to remote
        copy_result = subprocess.run(["rclone", "copyto", temp_path, filepath], capture_output=True, text=True, timeout=15)
        os.unlink(temp_path)
        
        if copy_result.returncode != 0:
            logger.error(f"Failed to save answer for {filename}: {copy_result.stderr}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error saving answer: {e}")
        return False
