import os
import re
import time
import json
import logging
import threading
import feedparser
import datetime
from google import genai
from google.genai import types
from windows_toasts import Toast, WindowsToaster

from config import GEMINI_API_KEY, ASSET_RADAR_DIR

logger = logging.getLogger(__name__)
client = genai.Client(api_key=GEMINI_API_KEY)

# A file to keep track of processed article links so we don't spam the user
RADAR_CACHE_FILE = os.path.join(ASSET_RADAR_DIR, ".radar_cache.json")
RADAR_REPORT_FILE = os.path.join(ASSET_RADAR_DIR, "雷达预警报告.md")

def load_cache():
    if os.path.exists(RADAR_CACHE_FILE):
        try:
            with open(RADAR_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_cache(cache):
    try:
        with open(RADAR_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as e:
        logger.error(f"Failed to save radar cache: {e}")

def send_desktop_alert(title, content, link):
    """Sends a desktop notification using windows-toasts and saves to Obsidian."""
    # 1. Desktop Notification in a separate thread so it doesn't block the pipeline
    def trigger_toast():
        try:
            toaster = WindowsToaster('AI Brain 资产雷达')
            t = Toast()
            t.text_fields = [f'🚨 {title}', '请前往 Obsidian 查看详情！']
            toaster.show_toast(t)
            logger.info("Successfully sent desktop alert.")
        except Exception as e:
            logger.error(f"Failed to send desktop alert: {e}")
            
    threading.Thread(target=trigger_toast, daemon=True).start()

    # 2. Append to Radar Report in Obsidian
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_content = f"## 🚨 预警时间: {timestamp}\n"
        report_content += f"### [{title}]({link})\n"
        report_content += f"{content}\n\n---\n"
        
        if not os.path.exists(RADAR_REPORT_FILE):
            with open(RADAR_REPORT_FILE, "w", encoding="utf-8") as f:
                f.write(f"---\n创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n标签: #预警报告 #宏观雷达\n---\n# 📉 宏观预警与黑天鹅雷达报告\n\n本页面由 `asset_radar.py` 自动维护。当发现重大宏观风险时，会自动在此处追加报告。\n\n---\n\n")
                
        with open(RADAR_REPORT_FILE, "a", encoding="utf-8") as f:
            f.write(report_content)
        logger.info(f"Successfully saved alert to {RADAR_REPORT_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save alert to Obsidian: {e}")
        return False

def extract_rss_urls_from_dir(directory: str) -> list[str]:
    """Reads all markdown files in the directory and extracts unique HTTP URLs."""
    if not os.path.isdir(directory):
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
                        urls.add(url)
            except Exception:
                pass
    return list(urls)

def fetch_recent_entries(urls: list[str], hours_ago: int = 2) -> list[dict]:
    """Fetches entries from RSS URLs published within the last N hours."""
    recent_entries = []
    cutoff_time = time.time() - (hours_ago * 3600)
    
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                pub_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = time.mktime(entry.published_parsed)
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    pub_time = time.mktime(entry.updated_parsed)
                    
                if pub_time and pub_time >= cutoff_time:
                    title = entry.get('title', 'No Title')
                    link = entry.get('link', url)
                    description = entry.get('summary', '') or entry.get('description', '')
                    recent_entries.append({
                        'feed_title': feed.feed.get('title', url),
                        'title': title,
                        'link': link,
                        'description': description,
                        'published': pub_time
                    })
        except Exception as e:
            logger.error(f"Asset Radar failed to parse feed {url}: {e}")
    return recent_entries

def analyze_macro_risk(entry: dict) -> dict | None:
    """Uses Gemini to evaluate if the news is a critical macro/asset risk."""
    full_text = f"Title: {entry['title']}\n\nSummary: {entry['description'][:3000]}"
    
    prompt = f"""You are a highly sophisticated macro-economic and strategic risk analyst (like Charlie Munger or Ray Dalio).
Your task is to analyze this financial/news update and determine if it represents a TRUE STRATEGIC RISK or MACRO SHIFT.

Look for:
1. Super-bubble popping signals (major market crashes, liquidity crises).
2. Tech supply chain severe disruptions (TSMC, Apple, Nvidia, major geopolitical bans).
3. Extreme valuation anomalies or systemic bank runs.

Ignore:
1. Normal daily stock market fluctuations (e.g., "S&P 500 down 1%").
2. Standard political drama or retail investor panic.
3. Routine earnings reports unless they signal a systemic collapse.

Respond STRICTLY in JSON format:
{{
    "is_critical_alert": true/false,
    "risk_level": "High/Medium/Low",
    "chinese_title": "Translated Title",
    "analysis": "2-3 sentences explaining exactly why this is a strategic risk, and how it impacts leverage/assets (in Chinese)."
}}

Article text:
{full_text}
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini Risk Analysis failed for '{entry['title']}': {e}")
        return None

def process_asset_radar():
    """Main pipeline for the Asset Radar."""
    logger.info("📡 Starting Asset Radar Sweep...")
    
    urls = extract_rss_urls_from_dir(ASSET_RADAR_DIR)
    if not urls:
        logger.info("No Radar URLs configured.")
        return
        
    cache = load_cache()
    # Sweep last 2 hours (since the scheduler runs every 2 hours)
    entries = fetch_recent_entries(urls, hours_ago=2.5) 
    
    new_alerts = 0
    for entry in entries:
        link = entry['link']
        if link in cache:
            continue
            
        logger.info(f"Radar Scanning: {entry['title']}")
        analysis = analyze_macro_risk(entry)
        
        if analysis and analysis.get("is_critical_alert") is True:
            logger.warning(f"🚨 CRITICAL MACRO RISK DETECTED: {entry['title']}")
            
            # Send alert
            success = send_desktop_alert(
                title=analysis.get('chinese_title', entry['title']),
                content=f"**风险等级**: {analysis.get('risk_level', 'High')}\n\n**深度分析**: {analysis.get('analysis', '')}",
                link=link
            )
            if success:
                new_alerts += 1
                
        # Always cache processed links to avoid re-evaluating
        cache.append(link)
        
    # Keep cache manageable (last 500 entries)
    if len(cache) > 500:
        cache = cache[-500:]
        
    save_cache(cache)
    logger.info(f"📡 Asset Radar Sweep finished. Triggered {new_alerts} alerts.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    process_asset_radar()
