import os
import glob
import shutil
import logging
from config import OBSIDIAN_BASE_PATH

logger = logging.getLogger(__name__)

def process_conflict_resolution():
    """
    Scans the entire Obsidian vault for files matching '*(conflict*'.
    Compares the modification time of the conflict file and the original file.
    If the conflict file is newer, it overwrites the original file.
    Then the conflict file is deleted.
    """
    logger.info("⚔️ Scanning for DriveSync conflict files...")
    
    # Use glob to find all conflict files recursively
    search_pattern = os.path.join(OBSIDIAN_BASE_PATH, "**", "*(conflict*")
    conflict_files = glob.glob(search_pattern, recursive=True)
    
    if not conflict_files:
        return
        
    logger.info(f"Found {len(conflict_files)} conflict files. Processing...")
    
    resolved_count = 0
    deleted_count = 0
    
    for conflict_path in conflict_files:
        try:
            # Example filename: "财商知识 (conflict 2026-08-11-21-02-31).md"
            # We want to extract "财商知识" and ".md" to reconstruct the original path
            
            dirname = os.path.dirname(conflict_path)
            basename = os.path.basename(conflict_path)
            
            # Split by " (conflict"
            parts = basename.split(" (conflict")
            if len(parts) != 2:
                logger.warning(f"Could not parse original name from {basename}. Skipping.")
                continue
                
            original_name_base = parts[0]
            
            # Extract extension (if any)
            ext_parts = parts[1].split(")")
            extension = ext_parts[-1] if len(ext_parts) > 1 else ""
            
            original_basename = f"{original_name_base}{extension}"
            original_path = os.path.join(dirname, original_basename)
            
            # If the original file exists, compare content length then times
            if os.path.exists(original_path):
                # Compare by content length (user requested: whichever checklist is longer)
                with open(conflict_path, "r", encoding="utf-8") as f:
                    conflict_len = len(f.read())
                with open(original_path, "r", encoding="utf-8") as f:
                    original_len = len(f.read())
                
                conflict_mtime = os.path.getmtime(conflict_path)
                original_mtime = os.path.getmtime(original_path)
                
                # Primary metric: length
                if conflict_len > original_len:
                    logger.info(f"Conflict file is LONGER ({conflict_len} > {original_len}). Overwriting: {original_basename}")
                    shutil.copy2(conflict_path, original_path)
                    os.remove(conflict_path)
                    resolved_count += 1
                elif original_len > conflict_len:
                    logger.info(f"Original file is LONGER ({original_len} > {conflict_len}). Deleting conflict: {basename}")
                    os.remove(conflict_path)
                    deleted_count += 1
                else:
                    # Fallback metric: modification time if lengths are identical
                    if conflict_mtime > original_mtime:
                        logger.info(f"Lengths equal. Conflict file is NEWER. Overwriting: {original_basename}")
                        shutil.copy2(conflict_path, original_path)
                        os.remove(conflict_path)
                        resolved_count += 1
                    else:
                        logger.info(f"Lengths equal. Original file is newer/same. Deleting conflict: {basename}")
                        os.remove(conflict_path)
                        deleted_count += 1
            else:
                # Original file doesn't exist (maybe renamed?). Just rename conflict to original
                logger.info(f"Original file missing. Renaming conflict back to: {original_basename}")
                os.rename(conflict_path, original_path)
                resolved_count += 1
                
        except Exception as e:
            logger.error(f"Error processing conflict file {conflict_path}: {e}")
            
    logger.info(f"⚔️ Conflict resolution complete. Overwrote/Renamed: {resolved_count}, Deleted obsolete: {deleted_count}.")
