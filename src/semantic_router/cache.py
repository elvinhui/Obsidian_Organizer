import os
import json
import hashlib
import yaml
from google import genai
from dotenv import load_dotenv

CACHE_FILE = ".prompt_cache.json"

def get_file_md5(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def extract_description(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        if content.startswith('---'):
            try:
                # Find the second '---'
                end = content.find('---', 3)
                if end != -1:
                    frontmatter = content[3:end]
                    data = yaml.safe_load(frontmatter)
                    return data.get('description', '')
            except Exception as e:
                pass
    return ""

def update_cache(prompts_dir="Templates/Prompts", api_key=None):
    if not api_key:
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        
    client = genai.Client(api_key=api_key)
    
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    else:
        cache = {}
        
    if not os.path.exists(prompts_dir):
        os.makedirs(prompts_dir, exist_ok=True)
        
    updated = False
    
    for filename in os.listdir(prompts_dir):
        if not filename.endswith('.md'):
            continue
            
        # Store relative paths in cache to allow moving the project
        filepath = os.path.join(prompts_dir, filename).replace('\\', '/')
        file_md5 = get_file_md5(filepath)
        
        # Check if needs update
        if filepath in cache and cache[filepath].get("md5") == file_md5:
            continue
            
        description = extract_description(filepath)
        if not description:
            print(f"Skipping {filename}, no description found.")
            continue
            
        print(f"Generating embedding for {filename.encode('utf-8', 'replace')}...")
        import time
        time.sleep(2)
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.embed_content(
                    model="models/gemini-embedding-001",
                    contents=description
                )
                embedding = response.embeddings[0].values
                
                cache[filepath] = {
                    "md5": file_md5,
                    "description": description,
                    "embedding": embedding
                }
                updated = True
                break
            except Exception as e:
                if '429' in str(e):
                    print(f"Rate limited. Waiting 15 seconds before retry {attempt+1}/{max_retries}...")
                    time.sleep(15)
                else:
                    print(f"Error embedding {filename.encode('utf-8', 'replace')}: {e}")
                    break

        
    # Remove deleted files
    current_files = [os.path.join(prompts_dir, f).replace('\\', '/') for f in os.listdir(prompts_dir) if f.endswith('.md')]
    to_delete = [f for f in cache.keys() if f not in current_files]
    for f in to_delete:
        print(f"Removing deleted file from cache: {f}")
        del cache[f]
        updated = True
        
    if updated:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print("Cache updated successfully.")
    else:
        print("Cache is already up to date.")
            
    return cache

if __name__ == "__main__":
    update_cache()
