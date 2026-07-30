import os
import re
import time
import logging
from uuid import uuid4
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
INBOX_DIR = os.getenv("INBOX_DIR")

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


def classify_and_save(content: str):
    """Uses Gemini to classify content into an inbox category and writes it."""
    prompt = f"""你是一个智能分类助手。你需要将用户发送的内容分类到以下三个 Obsidian 收件箱文件中：
1. AI.md (如果是关于人工智能、大模型、AI工具的内容)
2. 财商知识.md (如果是关于投资、理财、商业、经济的内容)
3. 认知提升.md (如果是关于个人成长、思维模型、心理学、其他无法分类的通用内容)

用户输入内容:
{content}

请只返回目标文件名（如：AI.md 或 财商知识.md 或 认知提升.md），不要输出任何其他多余字符。
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1)
        )
        category = response.text.strip()
        
        # Fallback safeguard
        if category not in ["AI.md", "财商知识.md", "认知提升.md"]:
            category = "认知提升.md"
            
        logger.info(f"Classified as: {category}")
        
        filepath = os.path.join(INBOX_DIR, category)
        
        # Append as a task
        # Remove line breaks from content so it fits nicely on one line, or format it
        safe_content = content.replace('\n', ' ')
        current_time = time.strftime("%Y-%m-%d %H:%M")
        task_entry = f"- [ ] #待处理 {current_time} | {safe_content}\n"
        
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(task_entry)
            
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
    category = classify_and_save(text)
    
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
        transcript = upload_and_process_with_gemini(temp_path, prompt)
        
        logger.info(f"Voice transcript: {transcript}")
        await update.message.reply_text(f"🎙️ 听写完成：\n{transcript}\n\n正在进行分类入库...")
        
        category = classify_and_save(f"[语音记录] {transcript}")
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
        summary = upload_and_process_with_gemini(temp_path, prompt)
        
        logger.info(f"Document summary: {summary}")
        await update.message.reply_text(f"📄 文档摘要：\n{summary}\n\n正在进行分类入库...")
        
        category = classify_and_save(f"[文档: {filename}] {summary}")
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
