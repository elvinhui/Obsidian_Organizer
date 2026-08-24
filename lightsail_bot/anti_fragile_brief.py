import os
import re
import time
import json
import logging
import datetime
import feedparser
from google import genai
from google.genai import types
from jinja2 import Template

logger = logging.getLogger(__name__)

# Note: this module will be run in the context of telegram_bot.py on the Lightsail server.
import subprocess

def extract_rss_urls_from_dir(directory: str) -> list[str]:
    urls = set()
    url_pattern = re.compile(r'https?://[^\s)\]"\']+')
    
    # 1. Try Native OS First
    if os.path.isdir(directory):
        for filename in os.listdir(directory):
            if filename.endswith(".md"):
                filepath = os.path.join(directory, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        found = url_pattern.findall(content)
                        for url in found:
                            urls.add(url)
                except Exception as e:
                    logger.error(f"Failed to read RSS source file {filename}: {e}")
        
        if urls:
            return list(urls)
            
    # 2. Fallback to rclone (FUSE mount might be inaccessible due to permissions)
    logger.info("Native OS read failed or returned empty. Attempting rclone fallback...")
    try:
        from telegram_bot import mount_path_to_remote
        remote_dir = mount_path_to_remote(directory)
        
        result = subprocess.run(["rclone", "lsf", remote_dir], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.split('\n') if f.strip().endswith('.md')]
            for filename in files:
                cat_result = subprocess.run(["rclone", "cat", f"{remote_dir}/{filename}"], capture_output=True, text=True, timeout=15)
                if cat_result.returncode == 0:
                    found = url_pattern.findall(cat_result.stdout)
                    for url in found:
                        urls.add(url)
    except Exception as e:
        logger.error(f"Rclone fallback failed: {e}")
        
    return list(urls)

def fetch_recent_entries(urls: list[str], hours_ago: int = 24) -> list[dict]:
    recent_entries = []
    cutoff_time = time.time() - (hours_ago * 3600)
    for url in urls:
        logger.info(f"Parsing RSS feed: {url}")
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
                    content = entry.content[0].value if hasattr(entry, 'content') else ""
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

def score_signal_to_noise(client, entry: dict) -> dict | None:
    full_text = f"Title: {entry['title']}\n\nSummary: {entry['description'][:2000]}\n\nContent: {entry['content'][:3000]}"
    prompt = f"""You are an elite cognitive coach and information filter. Your job is to strictly evaluate the following article based on its "Signal-to-Noise Ratio" (SNR) and "Anti-Fragility" value.
Evaluate if it contains profound philosophical insights, hard science, wealth-building principles, or AI system-design knowledge. Ignore clickbait, news recaps, drama, or shallow tips.
Rate the article from 1 to 10. If the score is 8 or above, extract the core thesis in Chinese. Respond strictly in JSON.

{{
    "score": 8,
    "reasoning": "Brief explanation",
    "chinese_title": "Translated or refined title",
    "core_thesis": "The most important 1-2 sentence takeaway (in Chinese)"
}}

Article text:
{full_text}"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "score": types.Schema(type=types.Type.INTEGER),
                        "reasoning": types.Schema(type=types.Type.STRING),
                        "chinese_title": types.Schema(type=types.Type.STRING),
                        "core_thesis": types.Schema(type=types.Type.STRING)
                    },
                    required=["score", "reasoning", "chinese_title", "core_thesis"]
                ),
                temperature=0.3
            )
        )
        
        raw_text = response.text.strip()
        if raw_text.startswith("```json"): raw_text = raw_text[7:]
        if raw_text.startswith("```"): raw_text = raw_text[3:]
        if raw_text.endswith("```"): raw_text = raw_text[:-3]
        return json.loads(raw_text.strip())
    except Exception as e:
        logger.error(f"Gemini SNR scoring failed for '{entry['title']}': {e}")
        return None

def generate_cross_comparison(client, high_quality_entries: list[dict]) -> dict:
    if not high_quality_entries:
        return {}
        
    combined_context = ""
    for idx, entry in enumerate(high_quality_entries):
        combined_context += f"\n--- Article {idx+1} ---\nSource: {entry['feed_title']}\nTitle: {entry['analysis'].get('chinese_title')}\nThesis: {entry['analysis'].get('core_thesis')}\n"
        
    prompt = f"""You are a master strategist, investor, and philosopher, combining the mindsets of Charlie Munger, Ray Dalio, and Naval Ravikant.
I have filtered today's highest-signal articles. I need you to synthesize them using the "天地人" (Heaven, Earth, Man) framework to create an Anti-Fragile Morning Briefing.

- 天 (Macro/Heaven): What are the macroscopic trends, AI paradigm shifts, or economic cycles discussed across these articles?
- 地 (Industry/Earth): What are the specific industry dynamics, supply chain issues, or company-level game theory happening?
- 人 (Individual/Man): What is the specific cognitive mental model, self-improvement, or philosophical action item we can take from this?

Cross-compare the ideas where possible. Don't just list them; integrate them into profound insights.

Return JSON strictly matching this schema:
{{
    "macro_heaven": "Insight about macro trends...",
    "industry_earth": "Insight about industry dynamics...",
    "individual_man": "Insight for personal cognitive growth...",
    "key_takeaway": "One final golden rule for today."
}}

Context:
{combined_context}"""

    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash', # Pro can be slow for timeouts, using flash for safety on scheduled tasks
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "macro_heaven": types.Schema(type=types.Type.STRING),
                        "industry_earth": types.Schema(type=types.Type.STRING),
                        "individual_man": types.Schema(type=types.Type.STRING),
                        "key_takeaway": types.Schema(type=types.Type.STRING)
                    },
                    required=["macro_heaven", "industry_earth", "individual_man", "key_takeaway"]
                ),
                temperature=0.7
            )
        )
        
        raw_text = response.text.strip()
        if raw_text.startswith("```json"): raw_text = raw_text[7:]
        if raw_text.startswith("```"): raw_text = raw_text[3:]
        if raw_text.endswith("```"): raw_text = raw_text[:-3]
        return json.loads(raw_text.strip())
    except Exception as e:
        logger.error(f"Gemini cross comparison failed: {e}")
        return {}

def generate_morning_briefing(client, rss_feeds_dir: str) -> str:
    logger.info("Starting Anti-Fragile Morning Brief generation...")
    urls = extract_rss_urls_from_dir(rss_feeds_dir)
    
    if not urls:
        return f"⚠️ 未找到任何配置的 RSS 订阅源。\n\n**系统诊断**：在 `{rss_feeds_dir}` 本地 FUSE 挂载和 `rclone` 备用通道均未找到有效的 RSS 链接 (.md文件中的http链接)。"
        
    entries = fetch_recent_entries(urls, hours_ago=24)
    high_quality_entries = []
    
    for entry in entries:
        analysis = score_signal_to_noise(client, entry)
        if analysis and analysis.get("score", 0) >= 8:
            entry['analysis'] = analysis
            high_quality_entries.append(entry)
            
    if not high_quality_entries:
        return "🧠 **今日反脆弱晨报**\n\n*今日无高分价值增量信息，保持大脑留白。*"
        
    logger.info(f"Generating cross-comparison for {len(high_quality_entries)} high-signal articles...")
    cross_analysis = generate_cross_comparison(client, high_quality_entries)
    
    template_str = """🧠 <b>【每日反脆弱认知晨报】</b> 🌞
为您挡住娱乐噪音，只留下能引发深度进化的信号。

{% if cross_analysis %}
🌍 <b>天 (宏观趋势 & 周期)</b>
{{ cross_analysis.macro_heaven }}

🏢 <b>地 (行业博弈 & 供应链)</b>
{{ cross_analysis.industry_earth }}

🧘 <b>人 (心智修炼 & 破局)</b>
{{ cross_analysis.individual_man }}

💡 <b>今日金句 (Key Takeaway)</b>
<i>{{ cross_analysis.key_takeaway }}</i>

—
{% endif %}
<b>🔥 今日高分信源清单：</b>
{% for entry in entries %}
• {{ entry.analysis.chinese_title }} (信噪比: {{ entry.analysis.score }}/10)
  🔗 <a href="{{ entry.link }}">原文链接</a>
  <i>{{ entry.analysis.core_thesis }}</i>
{% endfor %}"""
    
    template = Template(template_str)
    rendered = template.render(
        cross_analysis=cross_analysis,
        entries=high_quality_entries
    )
    return rendered
