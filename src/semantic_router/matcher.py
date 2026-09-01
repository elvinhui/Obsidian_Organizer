import json
import numpy as np
from google import genai
import os
from dotenv import load_dotenv

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".prompt_cache.json")

def get_query_embedding(query, api_key=None):
    if not api_key:
        load_dotenv()
        if not os.getenv("GEMINI_API_KEY"):
            load_dotenv("lightsail_bot/.env")
        api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    response = client.models.embed_content(
        model="models/gemini-embedding-001",
        contents=query
    )
    return response.embeddings[0].values

def cosine_similarity(vec_a, vec_b):
    dot_product = np.dot(vec_a, vec_b)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)

def llm_fallback_router(query, cache, api_key=None):
    if not api_key:
        load_dotenv()
        if not os.getenv("GEMINI_API_KEY"):
            load_dotenv("lightsail_bot/.env")
        api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    options = []
    for filepath, data in cache.items():
        # use basename for simpler LLM output
        options.append(f"Filename: {os.path.basename(filepath)}\nDescription: {data.get('description', '')}")
        
    prompt = (
        "You are a semantic router. Select the most appropriate prompt template for the user's text. "
        "Reply ONLY with the exact Filename. If none fit, reply 'None'.\n\n"
        "Options:\n" + "\n\n".join(options) + "\n\n"
        "User text: " + query
    )
    
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
        answer = response.text.strip()
        # map back to full path
        for filepath in cache.keys():
            if os.path.basename(filepath) == answer:
                return filepath, 0.9999
    except Exception as e:
        print(f"LLM fallback failed: {e}")
    return None, 0.0

def find_best_prompt(query, api_key=None):
    if not os.path.exists(CACHE_FILE):
        return None, 0.0
        
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)
        
    if not cache:
        return None, 0.0
        
    try:
        query_vec = np.array(get_query_embedding(query, api_key=api_key))
        
        best_filepath = None
        best_score = -1.0
        
        for filepath, data in cache.items():
            if "embedding" not in data:
                continue
            doc_vec = np.array(data["embedding"])
            score = float(cosine_similarity(query_vec, doc_vec))
            if score > best_score:
                best_score = score
                best_filepath = filepath
                
        return best_filepath, best_score
    except Exception as e:
        print(f"Embedding failed ({e}), falling back to LLM router...")
        return llm_fallback_router(query, cache, api_key=api_key)

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "我最近工作压力很大，老是焦虑"
    best_file, score = find_best_prompt(query)
    print(f"Best match: {best_file} (Score: {score:.4f})")
