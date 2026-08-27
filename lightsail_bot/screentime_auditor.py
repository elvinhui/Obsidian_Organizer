import os
import json
import logging
import datetime
import urllib.request
import urllib.parse
from google import genai

logger = logging.getLogger(__name__)

def fetch_rescuetime_data(api_key: str, target_date: str) -> str | None:
    """Fetches daily usage data from RescueTime API for a specific date (YYYY-MM-DD)."""
    # RescueTime Analytic API Endpoint
    url = "https://www.rescuetime.com/anapi/data"
    
    # Query parameters
    params = {
        "key": api_key,
        "format": "json",
        "resolution_time": "day",
        "restrict_begin": target_date,
        "restrict_end": target_date,
        "restrict_kind": "activity"
    }
    
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"
    
    try:
        req = urllib.request.Request(full_url, method='GET')
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                logger.error(f"RescueTime API returned status code {response.status}")
                return None
            
            data = json.loads(response.read().decode('utf-8'))
            rows = data.get("rows", [])
            
            if not rows:
                return "No data recorded for today."
                
            # Format rows for Gemini: [Rank, Time Spent (seconds), Number of People, Activity, Category, Productivity]
            formatted_data = []
            total_seconds = 0
            
            for row in rows:
                seconds_spent = row[1]
                activity_name = row[3]
                category_name = row[4]
                
                total_seconds += seconds_spent
                minutes = int(seconds_spent / 60)
                
                if minutes > 0: # Only list apps used for at least 1 minute
                    formatted_data.append(f"- {activity_name} ({category_name}): {minutes}m")
            
            total_hours = int(total_seconds / 3600)
            total_mins = int((total_seconds % 3600) / 60)
            
            summary = f"Total Screen Time: {total_hours}h {total_mins}m\n\nApp Breakdown:\n" + "\n".join(formatted_data)
            return summary
            
    except Exception as e:
        logger.error(f"Error fetching RescueTime data: {e}")
        return None

def generate_and_save_rescuetime_audit(api_key: str, gemini_api_key: str, base_path: str) -> str | None:
    """Fetches data, runs Gemini audit, saves to file, and returns the markdown report."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    raw_text = fetch_rescuetime_data(api_key, today_str)
    if not raw_text:
        logger.warning("No data retrieved from RescueTime, skipping audit.")
        return None
        
    logger.info("Successfully fetched RescueTime data, generating audit with Gemini...")
    
    prompt = f\"\"\"
    You are an elite productivity and digital minimalism auditor (like Ray Dalio / Cal Newport).
    Analyze the following raw notification containing daily screen time stats for Android.
    
    IMPORTANT: ONLY analyze the apps explicitly listed in the raw data. DO NOT invent, hallucinate, or add any apps that are not present in the data.
    
    Raw Data:
    {raw_text}
    
    Tasks:
    1. Identify the total screen time.
    2. Extract key apps and their usage times.
    3. Categorize them into:
       - 🎯 Core Tasks (efficiency, learning, coding, hard skills)
       - 🗣️ Essential Life/Communication (WeChat, tools, banking, transport)
       - 🛑 Distraction Noise (short videos, games, mindless feeds, social media)
    4. Calculate the S/N ratio (Signal to Noise Ratio) = Core Tasks duration / Distraction Noise duration. (If denominator is 0, write 'No Noise').
    5. Write a 2-sentence sharp, constructive CBT audit advice (in Chinese).
    6. Generate a beautiful markdown report (in Chinese).
    \"\"\"
    
    try:
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt
        )
        report_md = response.text
        
        # Save directly to FUSE
        target_dir = os.path.join(base_path, "03 资产库_Areas", "个人审计", "注意力审计")
        os.makedirs(target_dir, exist_ok=True)
        filepath = os.path.join(target_dir, f"注意力审计_{today_str}.md")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_md)
            f.flush()
            os.fsync(f.fileno())
            
        logger.info(f"Saved RescueTime audit to: {filepath}")
        return report_md
        
    except Exception as e:
        logger.error(f"Failed to generate/save RescueTime audit: {e}")
        return None
