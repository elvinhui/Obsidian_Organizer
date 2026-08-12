import os
import re
import time
import json
import logging
import feedparser
import datetime
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, RSS_FEEDS_DIR, DAILY_BRIEFING_DIR

logger = logging.getLogger(__name__)
client = genai.Client(api_key=GEMINI_API_KEY)

def extract_rss_urls_from_dir(directory: str) -> list[str]:
    """Reads all markdown files in the directory and extracts unique HTTP URLs."""
    if not os.path.isdir(directory):
        logger.warning(f"RSS directory {directory} does not exist.")
        return []
        
    urls = set()
    url_pattern = re.compile(r'https?://[^\s)\]"\']+')
    
    for filename in os.listdir(directory):
        if filename.endswith(".md"):
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    found = url_pattern.findall(content)
                    for url in found:
                        # Exclude common non-rss links if needed, but feedparser handles invalid gracefully
                        urls.add(url)
            except Exception as e:
                logger.error(f"Failed to read RSS source file {filename}: {e}")
                
    return list(urls)

def fetch_recent_entries(urls: list[str], hours_ago: int = 24) -> list[dict]:
    """Fetches entries from RSS URLs that were published within the last N hours."""
    recent_entries = []
    cutoff_time = time.time() - (hours_ago * 3600)
    
    for url in urls:
        logger.info(f"Parsing RSS feed: {url}")
        try:
            feed = feedparser.parse(url)
            if feed.bozo and hasattr(feed, 'bozo_exception'):
                # Bozo may be true for non-standard RSS, but it might still parse entries
                logger.debug(f"Feed parser warning for {url}: {feed.bozo_exception}")
                
            for entry in feed.entries:
                # Get publication timestamp
                pub_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = time.mktime(entry.published_parsed)
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    pub_time = time.mktime(entry.updated_parsed)
                    
                if pub_time and pub_time >= cutoff_time:
                    # Entry is recent
                    title = entry.get('title', 'No Title')
                    link = entry.get('link', url)
                    description = entry.get('summary', '') or entry.get('description', '')
                    content = ""
                    if hasattr(entry, 'content'):
                        content = entry.content[0].value
                        
                    recent_entries.append({
                        'feed_title': feed.feed.get('title', url),
                        'title': title,
                        'link': link,
                        'description': description,
                        'content': content,
                        'published': pub_time
                    })
        except Exception as e:
            logger.error(f"Failed to parse feed {url}: {e}")
            
    return recent_entries

def score_signal_to_noise(entry: dict) -> dict | None:
    """Uses Gemini to rate the signal-to-noise ratio of the article."""
    full_text = f"Title: {entry['title']}\n\nSummary: {entry['description'][:2000]}\n\nContent: {entry['content'][:5000]}"
    
    prompt = f"""You are an elite cognitive coach and information filter. Your job is to strictly evaluate the following article based on its "Signal-to-Noise Ratio" (SNR) and "Anti-Fragility" value.

Evaluate if it contains profound philosophical insights, hard science (neuroscience), wealth-building principles (finance/business), or AI system-design knowledge.
Ignore clickbait, news recaps, drama, or shallow tips.

Rate the article from 1 to 10.
If the score is 8 or above, provide a translated summary (in Chinese) and extract the core thesis.
If the score is below 8, keep the summary empty.

Respond strictly in JSON format:
{{
    "score": 8,
    "reasoning": "Brief explanation of the score",
    "chinese_title": "Translated or refined title",
    "core_thesis": "The most important 1-2 sentence takeaway (in Chinese)",
    "key_arguments": ["Argument 1", "Argument 2"]
}}

Article text:
{full_text}
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash', # Fast and cheap for filtering
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3
            )
        )
        data = json.loads(response.text)
        return data
    except Exception as e:
        logger.error(f"Gemini SNR scoring failed for '{entry['title']}': {e}")
        return None

def process_daily_rss_feeds():
    """Main pipeline for the daily RSS anti-fragile filter."""
    logger.info("🛡️ Starting Daily RSS Anti-Fragility Filter...")
    
    os.makedirs(DAILY_BRIEFING_DIR, exist_ok=True)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    daily_note_path = os.path.join(DAILY_BRIEFING_DIR, f"{today_str}.md")
    
    # 1. Check if we already processed today
    if os.path.exists(daily_note_path):
        with open(daily_note_path, "r", encoding="utf-8") as f:
            if "## 🧠 每日反脆弱认知简报" in f.read():
                logger.info(f"Today's RSS briefing is already generated in {daily_note_path}. Skipping.")
                return

    urls = extract_rss_urls_from_dir(RSS_FEEDS_DIR)
    if not urls:
        logger.info("No RSS feeds configured. Skipping.")
        return
        
    logger.info(f"Found {len(urls)} RSS URLs. Fetching recent entries (24h)...")
    entries = fetch_recent_entries(urls, hours_ago=24)
    logger.info(f"Fetched {len(entries)} recent articles. Filtering...")
    
    high_quality_briefs = []
    
    for entry in entries:
        logger.info(f"Scoring: {entry['title']}")
        analysis = score_signal_to_noise(entry)
        if analysis and analysis.get("score", 0) >= 8:
            logger.info(f"🔥 HIGH SIGNAL (Score {analysis['score']}): {entry['title']}")
            
            brief = f"### [{analysis.get('chinese_title', entry['title'])}]({entry['link']})\n"
            brief += f"**信源**: {entry['feed_title']} | **信噪比评分**: {analysis['score']}/10\n"
            brief += f"> **核心论点**: {analysis.get('core_thesis', '')}\n\n"
            if analysis.get('key_arguments'):
                for arg in analysis['key_arguments']:
                    brief += f"- {arg}\n"
            high_quality_briefs.append(brief)
        else:
            score = analysis.get('score', 'N/A') if analysis else 'Error'
            logger.debug(f"Filtered out (Score {score}): {entry['title']}")
            
    if not high_quality_briefs:
        logger.info("No high-quality articles passed the filter today.")
        briefing_content = "\n## 🧠 每日反脆弱认知简报\n*今日无高价值增量信息，保持大脑留白。*\n"
    else:
        briefing_content = "\n## 🧠 每日反脆弱认知简报\n> “为你挡住娱乐噪音，只留下能引发深度进化的信号。”\n\n"
        briefing_content += "\n\n".join(high_quality_briefs)
        
    # Append to daily note
    try:
        # Check if file exists, if not create with frontmatter
        if not os.path.exists(daily_note_path):
            with open(daily_note_path, "w", encoding="utf-8") as f:
                f.write(f"---\n创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n标签: #每日简报\n---\n# {today_str}\n")
                
        with open(daily_note_path, "a", encoding="utf-8") as f:
            f.write(briefing_content)
        logger.info(f"✅ Successfully appended RSS Briefing to {daily_note_path}")
    except Exception as e:
        logger.error(f"Failed to append to daily note: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    process_daily_rss_feeds()
