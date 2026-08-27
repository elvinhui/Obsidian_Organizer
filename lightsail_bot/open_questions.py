import os
import random
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

def get_open_questions_dir(base_path: str) -> str:
    """Gets the path to the open questions directory on FUSE."""
    return f"{base_path}/03 资产库_Areas/开放性思考"

def pick_random_unanswered_question(base_path: str) -> dict:
    """
    Picks a random question that is still marked as '状态: 持续迭代'.
    Returns a dict with filename and content, or None if all are answered.
    """
    local_dir = get_open_questions_dir(base_path)
    
    try:
        if not os.path.exists(local_dir):
            logger.warning(f"Open questions dir does not exist: {local_dir}")
            return None
            
        files = [f for f in os.listdir(local_dir) if f.endswith('.md')]
        unanswered_files = []
        
        for filename in files:
            filepath = os.path.join(local_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                if "状态: 持续迭代" in content:
                    unanswered_files.append({"filename": filename, "content": content, "filepath": filepath})
            except Exception as e:
                logger.error(f"Failed to read {filepath}: {e}")
                
        if not unanswered_files:
            return None
            
        pick = random.choice(unanswered_files)
        
        content = pick["content"]
        prompt_match = re.search(r'## ❓ 命题重述.*?>(.*?)(?:\n##|\Z)', content, re.DOTALL)
        if prompt_match:
            prompt_text = prompt_match.group(1).strip()
        else:
            prompt_text = content[:300] + "..."
            
        return {
            "filename": pick["filename"],
            "prompt": prompt_text,
            "full_content": content,
            "filepath": pick["filepath"]
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
        filepath = pick_data["filepath"]
        
        # Update state
        content = content.replace("状态: 持续迭代", "状态: 已回答")
        
        # Ensure target section exists and append
        target_section = "> **一句话回答：**"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        answer_block = f"\n\n**[{timestamp}] 我的3句话破局**\n{answer}\n"
        
        if target_section in content:
            content = content.replace(target_section, target_section + answer_block)
        else:
            content += f"\n\n{target_section}{answer_block}"
            
        # Write back via FUSE
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
            
        logger.info(f"Successfully saved answer to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Error saving answer: {e}")
        return False
