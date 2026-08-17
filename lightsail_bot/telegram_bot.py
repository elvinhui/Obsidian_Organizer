import os
import re
import time
import shutil
import subprocess
import logging
from uuid import uuid4
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        
        data = json.loads(response.text)
        category = data.get("category", "认知提升.md")
        
        if category == "IDEA" and IDEAS_DIR:
            # Generate the Markdown file for Idea
            import re
            raw_title = data.get("idea_title", "未命名灵感")
            title = re.sub(r'[\\/:*?"<>|]', '_', raw_title)
            current_time = time.strftime("%Y-%m-%d %H:%M")
            idea_type = data.get("idea_type", "🤔 纯粹的奇思妙想 (生活感悟)")
            idea_feasibility = data.get("idea_feasibility", "⭐⭐ 中等 (需要查资料/花几天时间)")
            idea_summary = data.get("idea_summary", content)
            idea_why = data.get("idea_why", "")
            idea_next_step = data.get("idea_next_step", "")
            
            md_content = f"---\n创建时间: {current_time}\n灵感分类: {idea_type}\n落地可行性: {idea_feasibility}\n---\n# 💡 {title}\n\n## 💭 这是个什么点子？(The Idea)\n> **一句话简述：** {idea_summary}\n\n## 🔗 为什么觉得它有用？(The Why)\n> **它能解决什么痛点？或者能带来什么好处？**\n- {idea_why}\n\n## 👣 下一步行动 (Next Step)\n> **如果要把这个灵感变成现实，我的第一个微小动作是什么？**\n- [ ] {idea_next_step}\n"
            
            filename = f"{title.strip()}.md"
            temp_path = f"/tmp/{uuid4()}_{filename}"
            final_path = os.path.join(IDEAS_DIR, filename)
            
            # Write to local /tmp first, then upload via rclone CLI (no FUSE conflicts)
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            rclone_write_new(temp_path, final_path)
            os.remove(temp_path)
            logger.info(f"Saved idea to: {final_path}")
            return "灵感库_Ideas"
            
        else:
            # Fallback safeguard
            if category not in ["AI.md", "财商知识.md", "认知提升.md"]:
                category = "认知提升.md"
                
            logger.info(f"Classified as: {category}")
            filepath = os.path.join(INBOX_DIR, category)
            
            safe_content = content.replace('\n', ' ')
            current_time = time.strftime("%Y-%m-%d %H:%M")
            task_entry = f"- [ ] #待处理 {current_time} | {safe_content}\n"
            
            # Use rclone CLI to append (read latest → append → upload)
            rclone_append(filepath, task_entry)
            return category
    except Exception as e:
        logger.error(f"Failed to classify and save: {e}")
        return None


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
            model='gemini-3.5-flash-lite',
            contents=[gemini_file, prompt]
        )
        return response.text
    finally:
        logger.info(f"Deleting file {gemini_file.name} from Gemini...")
        client.files.delete(name=gemini_file.name)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text("你好！我是你的 Obsidian Inbox 助理。发送文字、链接、语音或文档，我会自动帮你分类并写入到 Inbox 中。")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles standard text messages or links."""
    text = update.message.text
    logger.info(f"Received text: {text}")
    
    await update.message.reply_text("⏳ 正在思考如何分类并写入库中...")
    category = await asyncio.to_thread(classify_and_save, text)
    
    if category:
        await update.message.reply_text(f"✅ 已成功分类并记录到 [{category}]")
    else:
        await update.message.reply_text("❌ 分类或写入失败，请检查服务器日志。")


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


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))

    # Messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot is polling...")
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
