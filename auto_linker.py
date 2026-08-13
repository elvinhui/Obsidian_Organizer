"""
Knowledge Graph Blindspot Finder (formerly Auto-Linker)
Scans the skill library, uses NetworkX to build a topological graph of existing [[Wikilinks]],
generates vector embeddings for all cards using Gemini, and finds "Structural Holes" 
(cards that are semantically very similar but topologically disconnected).
Generates Zettelkasten-style "Bridge Notes" for the top structural holes.
"""

import os
import re
import json
import time
import logging
import numpy as np
import networkx as nx
from itertools import combinations
from google import genai
from google.genai import types

from config import SKILLS_DIR, GEMINI_API_KEY, INSIGHTS_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

# Cosine similarity threshold to consider two cards as a potential "Blindspot"
SIMILARITY_THRESHOLD = 0.85
# Max bridge notes to generate per run to avoid spamming the vault
MAX_BRIDGES_PER_RUN = 3

def extract_card_info(filepath: str) -> dict | None:
    """Extract title, core concepts, and existing links from a skill card."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        filename = os.path.basename(filepath)
        
        # Extract title (first # heading)
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else filename
        
        # Extract core concepts section (used for embeddings)
        core_match = re.search(r'##\s*💡.*?\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        core = core_match.group(1).strip() if core_match else content[:500]
        
        # Extract all [[links]]
        links = set(re.findall(r'\[\[(.+?)\]\]', content))
        # Remove .md if present in links
        links = {link.replace(".md", "") for link in links}
        
        return {
            "filename": filename,
            "title": title,
            "core": core,
            "links": links,
            "filepath": filepath,
            "full_content": content
        }
    except Exception as e:
        logger.error(f"Failed to extract info from {filepath}: {e}")
        return None

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate vector embeddings using Gemini API."""
    logger.info(f"Generating embeddings for {len(texts)} texts...")
    embeddings = []
    
    try:
        # Batch requests into chunks of 100
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            response = client.models.embed_content(
                model='models/gemini-embedding-001', 
                contents=batch
            )
            if hasattr(response, 'embeddings'):
                 for emb in response.embeddings:
                     embeddings.append(emb.values)
            elif isinstance(response, list):
                 for emb in response:
                     embeddings.append(emb.values if hasattr(emb, 'values') else emb)
        return embeddings
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        return [[0.0]*768 for _ in texts]

def generate_bridge_note(card_a: dict, card_b: dict) -> bool:
    """Uses Gemini PRO to analyze a structural hole and generates a Bridge Note."""
    logger.info(f"Generating Bridge Note for: {card_a['title']} <-> {card_b['title']}")
    
    prompt = f"""
    You are an elite Knowledge Graph Architect practicing the Zettelkasten method and Charlie Munger's mental models.
    I have two knowledge cards in my database that are mathematically highly similar (high vector similarity) 
    but topologically DISCONNECTED (no links between them). This is a "Structural Hole" or "Cognitive Blindspot".
    
    Your task is to write a "Bridge Note" (Zettelkasten MOC/Hub card) that connects them.
    
    Card A: {card_a['title']}
    Content: {card_a['core'][:1000]}
    
    Card B: {card_b['title']}
    Content: {card_b['core'][:1000]}
    
    Requirements for the Bridge Note:
    1. Title: Create a profound, cross-disciplinary title for this bridge (e.g., "[桥接] 复利与习惯的底层同构").
    2. Deep Diagnosis: Write a 100-200 word deep reflection on *why* these two are connected. What is the hidden causal chain, fundamental law, or complementary perspective?
    3. Output strictly as JSON.
    
    JSON Format:
    {{
        "bridge_title": "String",
        "diagnosis": "String"
    }}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4
            )
        )
        result = json.loads(response.text)
        
        bridge_title = result.get("bridge_title", f"[桥接] {card_a['title']} 与 {card_b['title']}")
        diagnosis = result.get("diagnosis", "AI failed to generate diagnosis.")
        
        safe_title = re.sub(r'[\\/:*?"<>|]', '-', bridge_title)
        bridge_filename = f"{safe_title}.md"
        os.makedirs(INSIGHTS_DIR, exist_ok=True)
        bridge_filepath = os.path.join(INSIGHTS_DIR, bridge_filename)
        
        if os.path.exists(bridge_filepath):
            logger.info(f"Bridge note already exists: {bridge_filename}")
            return False
            
        content = f"""# {bridge_title}

## 🌐 AI 认知盲区扫描 (Blindspot Diagnosis)

{diagnosis}

## 🔗 链接节点
- 节点 A: [[{card_a['filename'].replace('.md', '')}]]
- 节点 B: [[{card_b['filename'].replace('.md', '')}]]
"""
        with open(bridge_filepath, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
            
        logger.info(f"✅ Created Bridge Note: {bridge_filename}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to generate bridge note: {e}")
        return False

def process_auto_linking():
    """
    Main entry point for Knowledge Graph Blindspot Finder.
    """
    logger.info("🌐 Starting Knowledge Graph Blindspot Finder...")
    
    if not os.path.exists(SKILLS_DIR):
        logger.warning(f"Skills directory not found: {SKILLS_DIR}")
        return
        
    # Get valid files
    all_files = [
        f for f in os.listdir(SKILLS_DIR) 
        if f.endswith('.md') and not f.startswith('[已合并]') and not f.startswith('[桥接]')
    ]
    
    if len(all_files) < 2:
        logger.info("Not enough files for blindspot analysis.")
        return
        
    cards = []
    for fname in all_files:
        info = extract_card_info(os.path.join(SKILLS_DIR, fname))
        if info:
            cards.append(info)
            
    # 1. Build Graph Topology
    G = nx.Graph()
    # Map filename without .md to the full dict for easy lookup
    node_map = {c['filename'].replace('.md', ''): c for c in cards}
    
    for card in cards:
        node_id = card['filename'].replace('.md', '')
        G.add_node(node_id)
        for link in card['links']:
            if link in node_map: # Only add edges for files that exist in our valid set
                G.add_edge(node_id, link)
                
    # 2. Generate Embeddings
    texts_to_embed = [c['core'][:500] for c in cards] # Max 500 chars to save tokens
    embeddings = generate_embeddings(texts_to_embed)
    
    # 3. Find Structural Holes (Blindspots)
    blindspots = []
    
    for i, j in combinations(range(len(cards)), 2):
        node_a = cards[i]['filename'].replace('.md', '')
        node_b = cards[j]['filename'].replace('.md', '')
        
        # Check if they are already connected
        if G.has_edge(node_a, node_b):
            continue
            
        sim = cosine_similarity(embeddings[i], embeddings[j])
        if sim >= SIMILARITY_THRESHOLD:
            blindspots.append({
                "card_a": cards[i],
                "card_b": cards[j],
                "similarity": sim
            })
            
    # Sort by similarity descending
    blindspots.sort(key=lambda x: x["similarity"], reverse=True)
    
    logger.info(f"🔍 Found {len(blindspots)} potential blindspots (similarity >= {SIMILARITY_THRESHOLD}).")
    
    # 4. Generate Bridge Notes for top blindspots
    generated = 0
    for bs in blindspots:
        if generated >= MAX_BRIDGES_PER_RUN:
            logger.info("Reached maximum bridge notes for this run. Stopping early.")
            break
            
        success = generate_bridge_note(bs['card_a'], bs['card_b'])
        if success:
            generated += 1
            # Rate limit Gemini calls
            time.sleep(5)
            
    logger.info(f"\n🎉 Blindspot Finder complete! Generated {generated} Bridge Notes.")
