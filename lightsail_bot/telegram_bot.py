import os
import re
import time
import shutil
import subprocess
import logging
import datetime
import threading
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from google import genai
from google.genai import types
import asyncio

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
import json
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
INBOX_DIR = os.getenv("INBOX_DIR", "").strip()
IDEAS_DIR = os.getenv("IDEAS_DIR", "").strip()

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Verify environment
if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, INBOX_DIR]):
    logger.error("Missing required environment variables. Check .env file.")
    exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

MOUNT_POINT = "/mnt/gdrive"

raw_base_path = os.getenv("OBSIDIAN_BASE_PATH", "/mnt/gdrive/Obsidian/Knowledge Base").strip()
# Robust normalization: Split by / or \ and strip spaces from all components
path_parts = [p.strip() for p in re.split(r'[/\\]', raw_base_path) if p.strip()]
if raw_base_path.startswith("/") or raw_base_path.startswith("\\"):
    OBSIDIAN_BASE_PATH = "/" + "/".join(path_parts)
else:
    OBSIDIAN_BASE_PATH = "/".join(path_parts)
DAILY_NOTES_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "日记")
CHAT_ID_FILE = os.path.join(os.path.dirname(__file__), "registered_users.json")

HABITS_CONFIG = [
    {"id": "meditate", "name": "冥想 2 分钟", "time": "09:00"},
    {"id": "read", "name": "读书 5 分钟", "time": "14:00"},
    {"id": "nophone", "name": "不刷手机 5 分钟", "time": "20:00"},
    {"id": "stare", "name": "发呆 2 分钟", "time": "22:00"}
]


# ---------------------------------------------------------------------------
# Background HTTP Server for Mobile metrics (StayFree + MacroDroid HTTP POST)
# ---------------------------------------------------------------------------
def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode('utf-8')
    req = urllib.request.Request(
        url, data=data, 
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as response:
            logger.info("Audit telegram notification sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send telegram notification: {e}")

def process_audit_and_notify(text: str):
    logger.info("Starting background audit for received UsageStats...")
    
    # 1. Ask Gemini to audit
    prompt = f"""
    You are an elite productivity and digital minimalism auditor (like Ray Dalio / Cal Newport).
    Analyze the following raw notification containing daily screen time stats for Android.
    
    Raw Data:
    {text}
    
    Tasks:
    1. Identify the total screen time.
    2. Extract key apps and their usage times.
    3. Categorize them into:
       - 🎯 Core Tasks (efficiency, learning, coding, hard skills)
       - 🛡️ Essential Life/Communication (WeChat, tools, banking, transport)
       - 📵 Distraction Noise (short videos, games, mindless feeds, social media)
    4. Calculate the S/N ratio (Signal to Noise Ratio) = Core Tasks duration / Distraction Noise duration. (If denominator is 0, write 'No Noise').
    5. Write a 2-sentence sharp, constructive CBT audit advice (in Chinese).
    6. Generate a beautiful markdown report (in Chinese).
    """
    
    try:
        # Notify immediately that processing started
        users = get_registered_users()
        for chat_id in users:
            send_telegram_message(chat_id, "📊 收到手机应用使用时长数据，正在进行注意力审计与分类...")

        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt
        )
        report_md = response.text
        
        # 2. Save via rclone
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        filepath = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "个人审计", "注意力审计", f"注意力审计_{today_str}.md")
        
        # Write to temp file and copy
        temp_path = f"/tmp/audit_{today_str}_{uuid4()}.md"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(f"---\n创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n标签: #注意力审计 #数字极简\n---\n# 📊 注意力审计日报 ({today_str})\n\n" + report_md)
            
        subprocess.run(["rclone", "copyto", temp_path, mount_path_to_remote(filepath)], timeout=20)
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        logger.info(f"Attention audit report saved to GDrive: {filepath}")
        
        # 3. Notify users via TG
        if users:
            tg_text = f"✅ **今日注意力审计已完成！**\n\n报告已同步至 Obsidian：\n`注意力审计_{today_str}.md`"
            for chat_id in users:
                send_telegram_message(chat_id, tg_text)
                
    except Exception as e:
        logger.error(f"Failed background audit: {e}")
        users = get_registered_users()
        for chat_id in users:
            send_telegram_message(chat_id, f"❌ 注意力审计失败: {e}")

class UsageStatsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Clean console output
        logger.info("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format%args))

    def do_POST(self):
        if self.path == "/usagestats":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data)
                text = data.get("text", "")
                
                # Send the response immediately to MacroDroid (no timeout)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "received"}).encode('utf-8'))
                
                # Process in a background thread to not block HTTP connection
                threading.Thread(target=process_audit_and_notify, args=(text,), daemon=True).start()
                
            except Exception as e:
                logger.error(f"Error in web server POST handler: {e}")
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


def get_rclone_remote():
    """Detect the configured rclone remote name (e.g. 'gdrive:')."""
    try:
        result = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True, timeout=10)
        remotes = [r.strip() for r in result.stdout.strip().split('\n') if r.strip()]
        if remotes:
            logger.info(f"Detected rclone remote: {remotes[0]}")
            return remotes[0]
    except Exception as e:
        logger.warning(f"Could not detect rclone remote: {e}")
    return None


RCLONE_REMOTE = get_rclone_remote()


def mount_path_to_remote(mount_path):
    """Convert a local mount path to an rclone remote path."""
    rel = os.path.relpath(mount_path, MOUNT_POINT)
    return f"{RCLONE_REMOTE}{rel}"


def rclone_append(filepath, content):
    """Append content to a Google Drive file using rclone CLI (no FUSE conflicts)."""
    remote = mount_path_to_remote(filepath)
    logger.info(f"rclone_append to: {remote}")
    
    # Step 1: Read the latest version directly from Google Drive
    result = subprocess.run(
        ["rclone", "cat", remote],
        capture_output=True, timeout=30
    )
    existing = result.stdout.decode("utf-8") if result.returncode == 0 else ""
    
    # Step 2: Append new content
    updated = existing + content
    
    # Step 3: Upload back atomically via rclone rcat
    proc = subprocess.run(
        ["rclone", "rcat", remote],
        input=updated.encode("utf-8"), timeout=30
    )
    if proc.returncode == 0:
        logger.info("rclone_append succeeded.")
    else:
        logger.error(f"rclone_append failed: {proc.stderr}")
    return proc.returncode == 0


def rclone_write_new(local_path, dest_path):
    """Upload a new local file to Google Drive using rclone CLI."""
    remote = mount_path_to_remote(dest_path)
    logger.info(f"rclone_write_new to: {remote}")
    proc = subprocess.run(["rclone", "copyto", local_path, remote], timeout=30)
    if proc.returncode == 0:
        logger.info("rclone_write_new succeeded.")
    else:
        logger.error(f"rclone_write_new failed: {proc.stderr}")
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Registered Users Persistence (for scheduled pushes)
# ---------------------------------------------------------------------------
def register_user(chat_id: int):
    try:
        users = []
        if os.path.exists(CHAT_ID_FILE):
            with open(CHAT_ID_FILE, "r") as f:
                users = json.load(f)
        if chat_id not in users:
            users.append(chat_id)
            with open(CHAT_ID_FILE, "w") as f:
                json.dump(users, f)
            logger.info(f"Registered new user for scheduled pushes: {chat_id}")
    except Exception as e:
        logger.error(f"Failed to register user: {e}")

def get_registered_users() -> list[int]:
    try:
        if os.path.exists(CHAT_ID_FILE):
            with open(CHAT_ID_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read registered users: {e}")
    return []

# ---------------------------------------------------------------------------
# Daily Note & Habit Check-in Logic (Syncs via rclone)
# ---------------------------------------------------------------------------
def get_daily_note_content(date_str: str) -> tuple[str, bool]:
    """Reads daily note content from Google Drive, or returns a template if missing."""
    filepath = os.path.join(DAILY_NOTES_DIR, f"{date_str}.md")
    remote = mount_path_to_remote(filepath)
    
    logger.info(f"Reading daily note: {remote}")
    result = subprocess.run(["rclone", "cat", remote], capture_output=True, timeout=20)
    if result.returncode == 0:
        return result.stdout.decode("utf-8"), True
    else:
        # Generate initial template
        template = f"""---
创建时间: {date_str} 20:00
标签: #日记 #个人审计
---
# {date_str} 日记

## ⚡ 今日微习惯
"""
        for h in HABITS_CONFIG:
            template += f"- [ ] {h['name']}\n"
            
        template += "\n## ✍️ 日常记录\n\n"
        return template, False

def write_daily_note(date_str: str, content: str):
    """Saves updated daily note content back to Google Drive."""
    filepath = os.path.join(DAILY_NOTES_DIR, f"{date_str}.md")
    remote = mount_path_to_remote(filepath)
    
    # Write to a temp local file first
    temp_path = f"/tmp/daily_{date_str}_{uuid4()}.md"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    logger.info(f"Uploading daily note update: {remote}")
    subprocess.run(["rclone", "copyto", temp_path, remote], timeout=20)
    
    if os.path.exists(temp_path):
        os.remove(temp_path)

def check_habit_checked_local(date_str: str, habit_name: str, existing_files: set) -> tuple[bool, bool]:
    """Helper to check if a habit is checked off in a specific daily note."""
    filename = f"{date_str}.md"
    if filename not in existing_files:
        return False, False
        
    filepath = os.path.join(DAILY_NOTES_DIR, filename)
    try:
        # Note: Since FUSE might download the file when opening, we read it locally
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        pattern = rf"- \[x\]\s*{re.escape(habit_name)}"
        if re.search(pattern, content, re.IGNORECASE):
            return True, True
        return True, False
    except Exception as e:
        logger.debug(f"Failed to read local note {filename} for streak: {e}")
        return False, False

def calculate_habit_streak(habit_name: str) -> int:
    """Calculates the current continuous streak of a habit going backwards from today."""
    today = datetime.date.today()
    streak = 0
    
    # List files once to avoid repeated disk checks
    existing_files = set()
    if os.path.exists(DAILY_NOTES_DIR):
        try:
            existing_files = set(os.listdir(DAILY_NOTES_DIR))
        except Exception as e:
            logger.warning(f"Failed to list daily notes directory: {e}")
            
    for day_offset in range(30):
        check_date = today - datetime.timedelta(days=day_offset)
        date_str = check_date.strftime("%Y-%m-%d")
        
        exists, checked = check_habit_checked_local(date_str, habit_name, existing_files)
        
        if day_offset == 0:
            # If checking today, and it exists and is checked, count it.
            # If not checked or not existing today, we don't break the streak yet,
            # we just check starting from yesterday.
            if exists and checked:
                streak += 1
            continue
            
        if exists and checked:
            streak += 1
        else:
            # Streak broken!
            break
            
    return streak


def classify_and_save(content: str):
    """Uses Gemini to classify content into an inbox category or Idea, and writes it."""
    prompt = f"""你是一个智能分类助手。请根据用户输入，将其分类，并以 JSON 格式返回。

分类选项 (category 字段):
- "AI.md": 关于人工智能、大模型、AI工具的内容
- "财商知识.md": 关于投资、理财、商业、经济的内容
- "IDEA": 灵感、点子、创业想法、可以执行或者孵化的构想
- "认知提升.md": 个人成长、思维模型、心理学、其他无法分类的通用内容（不算是具体的IDEA的话）

如果 category 是 "IDEA"，你还必须根据以下字段提供结构化内容（否则可以为空）：
- "idea_title": 给这个灵感起个简短的名字 (核心词+场景)
- "idea_type": 从中选一个 ["🛠️ 自动化/代码构想 (提升效率)", "💼 职场/硬技能开发 (职业发展)", "💰 财富/资源优化 (资产配置)", "🤔 纯粹的奇思妙想 (生活感悟)"]
- "idea_feasibility": 从中选一个 ["⭐⭐⭐ 极高 (这周末就能搞定)", "⭐⭐ 中等 (需要查资料/花几天时间)", "⭐ 较低 (先存着，以后再说)"]
- "idea_summary": 用一句话概括这个灵感
- "idea_why": 它能解决什么痛点？或者能带来什么好处？(一段话)
- "idea_next_step": 如果要把这个灵感变成现实，我的第一个微小动作是什么？(一句话)

用户输入内容:
{content}
"""
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        
        raw_text = response.text
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        data = json.loads(raw_text.strip())
        category = data.get("category", "认知提升.md")
        
        if category == "IDEA" and IDEAS_DIR:
            import re
            raw_title = data.get("idea_title", "未命名灵感")
            title = re.sub(r'[\\/:*?"<>|]', '_', raw_title)
            current_time = time.strftime("%Y-%m-%d %H:%M")
            idea_type = data.get("idea_type", "🤔 纯粹的奇思妙想 (生活感悟)")
            idea_feasibility = data.get("idea_feasibility", "⭐⭐ 中等 (需要查资料/花几天时间)")
            idea_summary = data.get("idea_summary", content)
            idea_why = data.get("idea_why", "")
            idea_next_step = data.get("idea_next_step", "")
            
            md_content = f"""---
创建时间: {current_time}
灵感分类: {idea_type}
落地可行性: {idea_feasibility}
---
# 💡 {title}

## 💭 这是个什么点子？(The Idea)
> **一句话简述：** {idea_summary}

## 🔗 为什么觉得它有用？(The Why)
> **它能解决什么痛点？或者能带来什么好处？**
- {idea_why}

## 👣 下一步行动 (Next Step)
> **如果要把这个灵感变成现实，我的第一个微小动作是什么？**
- [ ] {idea_next_step}
"""
            filename = f"{title.strip()}.md"
            temp_path = f"/tmp/{uuid4()}_{filename}"
            final_path = os.path.join(IDEAS_DIR, filename)
            
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            rclone_write_new(temp_path, final_path)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            logger.info(f"Saved idea to: {final_path}")
            return "灵感库_Ideas"
            
        else:
            if category not in ["AI.md", "财商知识.md", "认知提升.md"]:
                category = "认知提升.md"
                
            logger.info(f"Classified as: {category}")
            filepath = os.path.join(INBOX_DIR, category)
            
            safe_content = content.replace('\n', ' ')
            current_time = time.strftime("%Y-%m-%d %H:%M")
            task_entry = f"- [ ] #待处理 {current_time} | {safe_content}\n"
            
            rclone_append(filepath, task_entry)
            return category
    except Exception as e:
        logger.error(f"Failed to classify and save: {e}")
        raise e

def upload_and_process_with_gemini(file_path: str, prompt: str) -> str:
    """Uploads a local file to Gemini and prompts it."""
    logger.info(f"Uploading {file_path} to Gemini...")
    gemini_file = client.files.upload(file=file_path)
    
    try:
        while gemini_file.state.name == "PROCESSING":
            logger.info("Waiting for file to be processed by Gemini...")
            time.sleep(3)
            gemini_file = client.files.get(name=gemini_file.name)
            
        if gemini_file.state.name == "FAILED":
            raise Exception("File processing failed on Gemini servers.")
            
        logger.info("Generating content...")
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[gemini_file, prompt]
        )
        return response.text
    finally:
        logger.info(f"Deleting file {gemini_file.name} from Gemini...")
        client.files.delete(name=gemini_file.name)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    chat_id = update.effective_chat.id
    register_user(chat_id)
    await update.message.reply_text(
        f"你好！我是你的 Obsidian Inbox 助理。\n\n"
        f"⚡ **微习惯系统已为你激活！**\n"
        f"ℹ️ **你的 Chat ID 是**：`{chat_id}` *(设置 MacroDroid 时可用此 ID)*\n\n"
        f"你可以发送 /habits 开启打卡看板。\n"
        f"我会在以下精力高峰期为你推送原子任务提醒：\n"
        f"1. 09:00 - 🧘 冥想 2 分钟\n"
        f"2. 14:00 - 📚 读书 5 分钟\n"
        f"3. 20:00 - 📵 不刷手机 5 分钟\n"
        f"4. 22:00 - 🌫️ 发呆 2 分钟\n\n"
        f"发送文字、链接、语音或文档，我会自动帮你分类并写入到 Inbox 中。",
        parse_mode="Markdown"
    )


async def handle_usage_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    logger.info("Received UsageStats report.")
    
    await update.message.reply_text("📊 收到应用使用时长数据，正在进行注意力审计与分类...")
    
    # 1. Ask Gemini to audit
    prompt = f"""
    You are an elite productivity and digital minimalism auditor (like Ray Dalio / Cal Newport).
    Analyze the following raw notification containing daily screen time stats for Android.
    
    Raw Data:
    {text}
    
    Tasks:
    1. Identify the total screen time.
    2. Extract key apps and their usage times.
    3. Categorize them into:
       - 🎯 Core Tasks (efficiency, learning, coding, hard skills)
       - 🛡️ Essential Life/Communication (WeChat, tools, banking, transport)
       - 📵 Distraction Noise (short videos, games, mindless feeds, social media)
    4. Calculate the S/N ratio (Signal to Noise Ratio) = Core Tasks duration / Distraction Noise duration. (If denominator is 0, write 'No Noise').
    5. Write a 2-sentence sharp, constructive CBT audit advice (in Chinese).
    6. Generate a beautiful markdown report (in Chinese).
    """
    
    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model='gemini-3.5-flash',
            contents=prompt
        )
        report_md = response.text
        
        # 2. Save via rclone
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        filepath = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "个人审计", "注意力审计", f"注意力审计_{today_str}.md")
        
        # Write to temp file and copy
        temp_path = f"/tmp/audit_{today_str}_{uuid4()}.md"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(f"---\n创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n标签: #注意力审计 #数字极简\n---\n# 📊 注意力审计日报 ({today_str})\n\n" + report_md)
            
        subprocess.run(["rclone", "copyto", temp_path, mount_path_to_remote(filepath)], timeout=20)
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        await update.message.reply_text(f"✅ 注意力审计已完成并保存至 Obsidian:\n`注意力审计_{today_str}.md`")
    except Exception as e:
        logger.error(f"Failed to audit usage stats: {e}")
        await update.message.reply_text(f"❌ 注意力审计失败: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles standard text messages or links."""
    text = update.message.text
    logger.info(f"Received text: {text}")
    
    if text.startswith("[UsageStats]"):
        await handle_usage_stats(update, context)
        return
        
    oq_pick = context.user_data.get('answering_oq')
    if oq_pick:
        await update.message.reply_text("⏳ 正在将您的回答归档到知识库...")
        try:
            from open_questions import save_answer
            import asyncio
            success = await asyncio.to_thread(save_answer, oq_pick, text)
            if success:
                await update.message.reply_text("✅ 回答已记录，该笔记状态已更新为「已回答」。")
                context.user_data.pop('answering_oq', None)
            else:
                await update.message.reply_text("❌ 保存失败，请查看服务器日志。")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error saving open question answer: {e}")
            await update.message.reply_text(f"❌ 发生错误：{e}")
        return
        
    await update.message.reply_text("⏳ 正在思考如何分类并写入库中...")
    try:
        # Wrap the blocking call in a wait_for to prevent infinite hanging
        category = await asyncio.wait_for(
            asyncio.to_thread(classify_and_save, text), 
            timeout=60.0
        )
        if category:
            await update.message.reply_text(f"✅ 已成功分类并记录到 [{category}]")
        else:
            await update.message.reply_text("❌ 分类或写入失败，请检查服务器日志。")
    except asyncio.TimeoutError:
        logger.error(f"classify_and_save timed out after 60s for text: {text}")
        await update.message.reply_text("❌ 处理超时（超过60秒），大模型API无响应，请稍后再试。")
    except Exception as e:
        logger.error(f"classify_and_save crashed: {e}")
        await update.message.reply_text(f"❌ 发生致命错误: {e}")


async def habits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send today's habits list with inline check-in buttons."""
    keyboard = []
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    content, existed = get_daily_note_content(today_str)
    
    # If note didn't exist, write template first
    if not existed:
        write_daily_note(today_str, content)
        
    # Check which habits are completed today
    for h in HABITS_CONFIG:
        pattern_done = rf"- \[x\]\s*{re.escape(h['name'])}"
        is_done = re.search(pattern_done, content, re.IGNORECASE) is not None
        
        status_icon = "✅" if is_done else "⬜"
        button_text = f"{status_icon} {h['name']}"
        callback_data = f"habit_done:{h['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚡ **今日微习惯打卡看板**\n请选择你已完成的原子习惯：",
        reply_markup=reply_markup
    )


async def habit_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles clicks on inline buttons for habit check-ins."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("habit_done:"):
        return
        
    habit_id = data.split(":")[1]
    habit = next((h for h in HABITS_CONFIG if h["id"] == habit_id), None)
    if not habit:
        return
        
    habit_name = habit["name"]
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    content, existed = get_daily_note_content(today_str)
    
    # Check if already completed
    pattern_done = rf"- \[x\]\s*{re.escape(habit_name)}"
    if re.search(pattern_done, content, re.IGNORECASE):
        await query.edit_message_text(f"✅ 你今天已经完成过【{habit_name}】了！")
        return
        
    # Replace - [ ] with - [x]
    pattern_todo = rf"- \[ \]\s*{re.escape(habit_name)}"
    updated_content = re.sub(pattern_todo, f"- [x] {habit_name}", content, flags=re.IGNORECASE)
    
    # Write back
    write_daily_note(today_str, updated_content)
    
    # Calculate Streak
    streak = calculate_habit_streak(habit_name)
    multiplier = (1.05 ** streak) if streak > 0 else 1.0
    
    reply_text = (
        f"🎉 **打卡成功！多巴胺 +1**\n\n"
        f"你已成功完成：**{habit_name}**\n"
        f"🔥 连续打卡天数：`{streak}` 天\n"
        f"📈 习惯复利系数：`{multiplier:.2f}x` (1.05^Streak)\n\n"
        f"*“每一天的微小累积，终将引发质变的洪流。”*"
    )
    
    await query.edit_message_text(reply_text, parse_mode="Markdown")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles voice messages."""
    voice = update.message.voice
    file_id = voice.file_id
    
    await update.message.reply_text("⏳ 收到语音，正在下载并进行 AI 听写...")
    
    new_file = await context.bot.get_file(file_id)
    ext = ".ogg"
    temp_path = f"/tmp/{uuid4()}{ext}"
    
    try:
        await new_file.download_to_drive(temp_path)
        logger.info(f"Voice downloaded to {temp_path}")
        
        prompt = "请将这段语音转写为纯文本。不要做任何润色，直接输出逐字稿即可。"
        transcript = await asyncio.to_thread(upload_and_process_with_gemini, temp_path, prompt)
        
        logger.info(f"Voice transcript: {transcript}")
        await update.message.reply_text(f"🎙️ 听写完成：\n{transcript}\n\n正在进行分类入库...")
        
        category = await asyncio.to_thread(classify_and_save, f"[语音记录] {transcript}")
        if category:
            await update.message.reply_text(f"✅ 已记录到 [{category}]")
            
    except Exception as e:
        logger.error(f"Voice processing failed: {e}")
        await update.message.reply_text("❌ 语音处理失败。")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles document uploads (PDF, DOC)."""
    document = update.message.document
    file_id = document.file_id
    filename = document.file_name
    
    await update.message.reply_text(f"⏳ 收到文档 {filename}，正在进行 AI 解析...")
    
    new_file = await context.bot.get_file(file_id)
    # Ensure safe extension for Gemini
    ext = os.path.splitext(filename)[1].lower()
    temp_path = f"/tmp/{uuid4()}{ext}"
    
    try:
        await new_file.download_to_drive(temp_path)
        logger.info(f"Document downloaded to {temp_path}")
        
        prompt = "请提取并总结这份文档的核心内容，输出一段精准的摘要，字数控制在200字以内。"
        summary = await asyncio.to_thread(upload_and_process_with_gemini, temp_path, prompt)
        
        logger.info(f"Document summary: {summary}")
        await update.message.reply_text(f"📄 文档摘要：\n{summary}\n\n正在进行分类入库...")
        
        category = await asyncio.to_thread(classify_and_save, f"[文档: {filename}] {summary}")
        if category:
            await update.message.reply_text(f"✅ 已记录到 [{category}]")
            
    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        await update.message.reply_text("❌ 文档处理失败。目前大模型主要支持 PDF 和常见文档格式。")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
async def trigger_brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger the morning brief."""
    if update.effective_chat.id not in get_registered_users():
        await update.message.reply_text("⛔ 未经授权的用户。")
        return
        
    await update.message.reply_text("🔄 正在手动生成晨报，请稍候（可能需要 1-2 分钟）...")
    
    try:
        from anti_fragile_brief import generate_morning_briefing
        rss_dir = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "RSS Feed")
        briefing_text = await asyncio.to_thread(generate_morning_briefing, client, rss_dir)
        await update.message.reply_text(briefing_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to generate manual brief: {e}")
        await update.message.reply_text(f"⚠️ 生成晨报时发生错误：{e}")

async def morning_brief_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running scheduled morning brief job...")
    users = get_registered_users()
    if not users:
        logger.warning("No registered users for morning brief.")
        return
        
    try:
        from anti_fragile_brief import generate_morning_briefing
        rss_dir = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "RSS Feed")
        
        # Run heavy I/O and LLM logic in a separate thread
        briefing_text = await asyncio.to_thread(generate_morning_briefing, client, rss_dir)
        
        # Send to all registered users
        for chat_id in users:
            try:
                await context.bot.send_message(chat_id=chat_id, text=briefing_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to send morning brief to {chat_id}: {e}")
                
        # Also save to Obsidian
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        daily_note_dir = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "每日简报")
        os.makedirs(daily_note_dir, exist_ok=True)
        daily_note_path = os.path.join(daily_note_dir, f"{today_str}.md")
        
        # We use sync file IO here because it's fast enough, but thread is safer
        def write_note():
            if not os.path.exists(daily_note_path):
                with open(daily_note_path, "w", encoding="utf-8") as f:
                    f.write(f"---\n创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n标签: #每日简报\n---\n# {today_str}\n")
            with open(daily_note_path, "a", encoding="utf-8") as f:
                f.write(f"\n{briefing_text}\n")
        
        await asyncio.to_thread(write_note)
        logger.info("Morning brief successfully generated and sent.")
        
    except ImportError:
        logger.error("Could not import generate_morning_briefing from anti_fragile_brief")
    except Exception as e:
        logger.error(f"Morning brief job failed: {e}")


def make_push_job(habit_item):
    async def push_job(context: ContextTypes.DEFAULT_TYPE):
        users = get_registered_users()
        if not users:
            logger.warning("No registered users to push habit reminders to.")
            return
            
        keyboard = [[InlineKeyboardButton("✅ 搞定打卡", callback_data=f"habit_done:{habit_item['id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        for chat_id in users:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚡ **微习惯时间提醒**\n现在是：**{habit_item['time']}**\n\n该去完成你的微习惯啦：\n👉 **{habit_item['name']}**\n\n最小化动作，立刻起步！",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send habit push to {chat_id}: {e}")
    return push_job



async def oq_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles clicks on 'Answer Open Question' button."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("answer_oq"):
        return
        
    if "oq_latest_pick" not in context.bot_data:
        await query.message.reply_text("❌ 题目已过期或丢失。")
        return
        
    context.user_data['answering_oq'] = context.bot_data["oq_latest_pick"]
    await query.message.reply_text("👇 请在下方直接输入您的回答（强制输出，建议不超过3句话）：")

async def open_question_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running scheduled open question job...")
    users = get_registered_users()
    if not users:
        return
        
    try:
        from open_questions import pick_random_unanswered_question
        import asyncio
        pick_data = await asyncio.to_thread(pick_random_unanswered_question, OBSIDIAN_BASE_PATH)
        
        if not pick_data:
            for chat_id in users:
                await context.bot.send_message(chat_id=chat_id, text="🎉 恭喜！所有的开放性思考题目都已回答完毕！积压清零！")
            return
            
        context.bot_data["oq_latest_pick"] = pick_data
        title = pick_data["filename"].replace(".md", "")
        prompt = pick_data["prompt"]
        
        message_text = f"💡 **【每日开放性思考】**\n\n**{title}**\n\n{prompt}"
        keyboard = [[InlineKeyboardButton("✍️ 开始回答 (限3句话)", callback_data="answer_oq")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        for chat_id in users:
            try:
                await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send open question to {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Open question job failed: {e}")

def main() -> None:
    """Start the bot."""
    # Start background HTTP server for mobile metrics (StayFree + MacroDroid)
    def start_http_server():
        try:
            server = HTTPServer(('0.0.0.0', 8080), UsageStatsHandler)
            logger.info("🚀 Background HTTP server listening on port 8080 for MacroDroid...")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start background HTTP server: {e}")
            
    threading.Thread(target=start_http_server, daemon=True).start()

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("habits", habits_command))
    application.add_handler(CommandHandler("brief", trigger_brief_command))

    # Messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Callbacks
    application.add_handler(CallbackQueryHandler(habit_callback_handler, pattern="^habit_done:"))
    application.add_handler(CallbackQueryHandler(oq_callback_handler, pattern="^answer_oq"))

    # Scheduled Pushes (UTC+8 / China Time)
    if application.job_queue:
        for h in HABITS_CONFIG:
            t_hour, t_min = map(int, h["time"].split(":"))
            t_time = datetime.time(hour=t_hour, minute=t_min, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
            job_func = make_push_job(h)
            application.job_queue.run_daily(job_func, time=t_time, name=f"push_habit_{h['id']}")
            
        # Morning Briefing Job (08:00 AM UTC+8)
        morning_brief_time = datetime.time(hour=8, minute=0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        application.job_queue.run_daily(morning_brief_job, time=morning_brief_time, name="morning_briefing")
        
        oq_time = datetime.time(hour=21, minute=0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        application.job_queue.run_daily(open_question_job, time=oq_time, name="open_question_push")
        
    else:
        logger.warning("JobQueue is not initialized! Scheduled pushes will not work. Please install python-telegram-bot[job-queue] on the server.")

    logger.info("Bot is polling...")
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
