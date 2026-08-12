"""
Telegram Bot interface for the Cognitive Debugger.
Runs as a long-polling bot alongside the main pipeline.
"""
import os
import sys
import logging
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from config import TELEGRAM_BOT_TOKEN
from cognitive_debugger.bot import CognitiveDebuggerBot, TOTAL_ROUNDS
from cognitive_debugger.prompts import ROUND_LABELS
from cognitive_debugger.session import archive_session

logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_WORRY, IN_SESSION = range(2)

# Store active sessions per user
user_sessions: dict[int, CognitiveDebuggerBot] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start and /debug commands."""
    await update.message.reply_text(
        "🧠 *认知调试器 \\(Cognitive Debugger\\)* 已启动\n\n"
        "我是你的苏格拉底式思维教练。当你陷入焦虑、内耗或灾难化想象时，"
        "我会通过 *五轮深度追问*，帮你从表层症状穿透至系统根因。\n\n"
        "💭 *请直接输入你现在正在烦恼的事情*，我会开始追问。\n"
        "🚪 输入 /cancel 随时退出。",
        parse_mode="MarkdownV2"
    )
    return WAITING_FOR_WORRY

async def receive_worry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the initial worry and start the session."""
    user_id = update.effective_user.id
    worry = update.message.text
    
    bot = CognitiveDebuggerBot()
    user_sessions[user_id] = bot
    
    await update.message.reply_text(f"📍 *{ROUND_LABELS[0]}*\n\n⏳ 苏格拉底正在思考...", parse_mode="Markdown")
    
    try:
        reply = bot.start_session(worry)
        await update.message.reply_text(f"🏛️ *苏格拉底：*\n\n{reply}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text(f"❌ API 调用出错: {e}\n请稍后再试。")
        return ConversationHandler.END
    
    return IN_SESSION

async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user responses during the session."""
    user_id = update.effective_user.id
    bot = user_sessions.get(user_id)
    
    if not bot:
        await update.message.reply_text("⚠️ 没有活跃的会话。请先发送 /debug 开始。")
        return ConversationHandler.END
    
    user_input = update.message.text
    current_round = bot.current_round
    
    if current_round < TOTAL_ROUNDS:
        await update.message.reply_text(f"📍 *{ROUND_LABELS[current_round]}*\n\n⏳ 深度分析中...", parse_mode="Markdown")
    else:
        await update.message.reply_text("📋 *正在生成认知调试报告...*", parse_mode="Markdown")
    
    try:
        reply = bot.next_round(user_input)
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text(f"❌ API 调用出错: {e}")
        return IN_SESSION
    
    if bot.is_complete:
        # Send the final report
        await update.message.reply_text(f"📋 *认知调试报告*\n\n{reply}", parse_mode="Markdown")
        
        # Archive to Obsidian
        try:
            dialogue_md = bot.get_full_dialogue_markdown()
            saved_path = archive_session(dialogue_md)
            if saved_path:
                await update.message.reply_text(f"✅ 会话已归档至 Obsidian:\n`{os.path.basename(saved_path)}`", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Archive failed: {e}")
        
        await update.message.reply_text("💡 _记住：你不是你的想法。想法只是天空中飘过的云，你是那片天空。_", parse_mode="Markdown")
        
        # Cleanup
        del user_sessions[user_id]
        return ConversationHandler.END
    else:
        await update.message.reply_text(f"🏛️ *苏格拉底：*\n\n{reply}", parse_mode="Markdown")
        return IN_SESSION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current session."""
    user_id = update.effective_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
    await update.message.reply_text("🚪 会话已结束。随时可以输入 /debug 重新开始。")
    return ConversationHandler.END

def run_telegram_bot():
    """Start the Telegram bot (blocking)."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Skipping Telegram bot.")
        return
    
    logger.info("🤖 Starting Cognitive Debugger Telegram Bot...")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("debug", start),
        ],
        states={
            WAITING_FOR_WORRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_worry)],
            IN_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_telegram_bot()
