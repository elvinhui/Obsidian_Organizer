import os
import sys
import logging
import datetime
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Config & Setup
# ---------------------------------------------------------------------------
load_dotenv()
# We use a distinct token for the Socrates bot so it can run alongside the main inbox bot
TELEGRAM_BOT_TOKEN = os.getenv("SOCRATES_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OBSIDIAN_BASE_PATH = os.getenv("OBSIDIAN_BASE_PATH", "/mnt/gdrive/Obsidian/Knowledge Base")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY]):
    logger.error("Missing SOCRATES_BOT_TOKEN or GEMINI_API_KEY. Check .env file.")
    exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)
DEBUGGER_ARCHIVE_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "认知调试记录")
COURT_ARCHIVE_DIR = os.path.join(OBSIDIAN_BASE_PATH, "03 资产库_Areas", "投资建议")

import asyncio

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """你是一位融合了苏格拉底式追问与认知行为治疗（CBT）的内心对话教练。
你的名字叫"认知调试器"。你不是一个温柔的安慰者——你是一个冷静的、善意的"思维外科医生"。

## 你的核心任务
当用户向你倾诉一个烦恼、焦虑或情绪困扰时，你必须执行**严格的五轮深度追问**，每一轮从不同的维度穿透用户的表层症状，直达系统根因。

## 五轮追问框架（必须严格遵守）

### 第1轮：定义问题（是什么）
- "你说的'X'，具体指的是什么？能描述一个最近发生的具体场景吗？"
- 目标：将模糊的焦虑感具体化为一个清晰的事件或念头。

### 第2轮：追溯原因（为什么）
- "你觉得这件事让你如此痛苦/焦虑的根本原因是什么？它触发了你内心的哪个恐惧？"
- 目标：从事件层穿透到情绪层，找到底层的恐惧或信念。

### 第3轮：质疑证据（证据在哪）
- "你说的这个担忧，有什么客观证据能支持它？有没有反面的证据？"
- 目标：检测认知扭曲（灾难化思维、非黑即白、读心术、过度概括等）。

### 第4轮：压力测试（最坏结果）
- "假设最坏的情况真的发生了，具体会怎样？你能承受吗？之后呢？"
- 目标：用"去灾难化"技术，让用户直面最坏结果并发现它并没有想象中那么致命。

### 第5轮：反转视角（如果反过来呢）
- "如果你最好的朋友遇到了一模一样的情况，你会怎么劝他/她？"
- 目标：利用"自我距离化"，让用户跳出当局者迷的陷阱。

## 认知扭曲检测清单
在对话过程中，你需要同时默默检测用户是否存在以下认知扭曲：
1. **灾难化思维**：把事情往最坏的方向想
2. **非黑即白**：只看到极端，没有中间地带
3. **读心术**：认定别人在想什么（通常是负面的）
4. **过度概括**：一件事推导出所有事
5. **贴标签**：用负面标签定义自己
6. **情绪推理**：因为我感到焦虑，所以事情一定很糟
7. **应该思维**：我"应该"怎样怎样

## 输出要求
- 每轮只问**一个核心问题**，不要一次倒出多个问题。
- 语气冷静、温和但坚定。像一个经验丰富的教练，不是居高临下的说教者。
- 使用中文回复。
- 适当使用 emoji 来调节氛围。
- 在你的回复中，先简短回应用户上一轮的回答（1-2句），然后抛出下一个追问。

## 最终报告
完成五轮追问后，你需要生成一份"认知调试报告"，格式如下：

```
## 🧠 认知调试报告

### 表层症状
（用户最初描述的问题）

### 根因分析
（通过五连问发现的深层原因）

### 检测到的认知扭曲
- [扭曲类型]：具体表现

### 现实检验结果
（最坏情况真的发生的概率 + 用户是否能承受）

### 行动建议
1. 立即可做的一件事
2. 本周可以尝试的一个改变
3. 长期需要建立的一个思维模型
```
"""

ROUND_LABELS = [
    "第1轮：定义问题（是什么）",
    "第2轮：追溯原因（为什么）",
    "第3轮：质疑证据（证据在哪）",
    "第4轮：压力测试（最坏结果）",
    "第5轮：反转视角（如果反过来呢）",
]

FINAL_PROMPT = """用户已经完成了五轮追问。现在请根据整个对话，生成一份完整的"认知调试报告"。
报告格式严格按照你的系统提示词中给出的模板。务必包含：
1. 表层症状
2. 根因分析
3. 检测到的认知扭曲（至少识别出1-2种）
4. 现实检验结果
5. 三条行动建议
用中文输出。"""

TOTAL_ROUNDS = 5

# ---------------------------------------------------------------------------
# Bot Engine
# ---------------------------------------------------------------------------
class CognitiveDebuggerBot:
    def __init__(self):
        self.current_round = 0
        self.history = []
        self.is_complete = False
        self.final_report = None
        
    def _build_contents(self):
        contents = []
        for msg in self.history:
            contents.append(types.Content(
                role=msg["role"],
                parts=[types.Part(text=msg["text"])]
            ))
        return contents
    
    def start_session(self, initial_worry: str) -> str:
        self.current_round = 1
        self.history = [{"role": "user", "text": initial_worry}]
        
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=self._build_contents(),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7
            )
        )
        reply = response.text
        self.history.append({"role": "model", "text": reply})
        return reply
    
    def next_round(self, user_response: str) -> str:
        self.current_round += 1
        self.history.append({"role": "user", "text": user_response})
        
        if self.current_round > TOTAL_ROUNDS:
            return self._generate_report()
        
        round_hint = f"\n[系统提示：现在进入{ROUND_LABELS[self.current_round - 1]}，请严格按照框架提问]"
        self.history[-1]["text"] += round_hint
        
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=self._build_contents(),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7
            )
        )
        reply = response.text
        self.history[-1]["text"] = self.history[-1]["text"].replace(round_hint, "")
        self.history.append({"role": "model", "text": reply})
        return reply
    
    def _generate_report(self) -> str:
        self.history[-1]["text"] += f"\n\n[系统提示：{FINAL_PROMPT}]"
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=self._build_contents(),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.5
            )
        )
        report = response.text
        self.history[-1]["text"] = self.history[-1]["text"].replace(f"\n\n[系统提示：{FINAL_PROMPT}]", "")
        self.history.append({"role": "model", "text": report})
        self.is_complete = True
        self.final_report = report
        return report
    
    def get_full_dialogue_markdown(self) -> str:
        md = "## 🧠 认知调试会话记录\n\n"
        round_num = 0
        for msg in self.history:
            text = msg["text"]
            if msg["role"] == "user" and not text.startswith("[系统提示") and not text.startswith("用户已经完成"):
                round_num += 1
                if round_num == 1:
                    md += f"### 初始烦恼\n> {text}\n\n"
                else:
                    md += f"### 第{round_num - 1}轮回答\n> {text}\n\n"
            elif msg["role"] == "model":
                md += f"{text}\n\n---\n\n"
        return md

def archive_session(dialogue_markdown: str):
    os.makedirs(DEBUGGER_ARCHIVE_DIR, exist_ok=True)
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H%M")
    date_str = now.strftime("%Y-%m-%d %H:%M")
    filename = f"认知调试_{timestamp}.md"
    filepath = os.path.join(DEBUGGER_ARCHIVE_DIR, filename)
    
    frontmatter = f"---\n创建时间: {date_str}\n标签: #认知调试 #五连问 #苏格拉底\n---\n"
    full_content = frontmatter + dialogue_markdown
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_content)
        logger.info(f"Session archived to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to archive session: {e}")
        return None

# ---------------------------------------------------------------------------
# Telegram Handlers
# ---------------------------------------------------------------------------
WAITING_FOR_WORRY, IN_SESSION = range(2)
user_sessions: dict[int, CognitiveDebuggerBot] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🧠 *认知调试器 (Cognitive Debugger)* 已启动\n\n"
        "我是你的苏格拉底式思维教练。当你陷入焦虑、内耗或灾难化想象时，"
        "我会通过 *五轮深度追问*，帮你从表层症状穿透至系统根因。\n\n"
        "💭 *请直接输入你现在正在烦恼的事情*，我会开始追问。\n"
        "🚪 输入 /cancel 随时退出。",
        parse_mode="Markdown"
    )
    return WAITING_FOR_WORRY

async def receive_worry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
        await update.message.reply_text(f"📋 *认知调试报告*\n\n{reply}", parse_mode="Markdown")
        
        try:
            dialogue_md = bot.get_full_dialogue_markdown()
            saved_path = archive_session(dialogue_md)
            if saved_path:
                await update.message.reply_text(f"✅ 会话已归档至 Obsidian:\n`{os.path.basename(saved_path)}`", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Archive failed: {e}")
        
        await update.message.reply_text("💡 _记住：你不是你的想法。想法只是天空中飘过的云，你是那片天空。_", parse_mode="Markdown")
        del user_sessions[user_id]
        return ConversationHandler.END
    else:
        await update.message.reply_text(f"🏛️ *苏格拉底：*\n\n{reply}", parse_mode="Markdown")
        return IN_SESSION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
    await update.message.reply_text("🚪 会话已结束。随时可以输入 /debug 重新开始。")
    return ConversationHandler.END

def _sync_court_agent_debate(topic: str):
    # Proponent
    proponent_prompt = f"你是一个法庭辩论中的【多头/正方】代言人。现在的命题是：{topic}\n请找出所有支持该决策的理由、潜在的宏观红利、以及乐观情况下的巨大收益。用有说服力、鼓动性的语言陈述，列出核心的3-5个论点。"
    pro_response = client.models.generate_content(
        model='gemini-3.5-flash-lite',
        contents=proponent_prompt,
        config=types.GenerateContentConfig(temperature=0.7)
    )
    proponent_arg = pro_response.text

    # Opponent
    opponent_prompt = f"你是一个法庭辩论中的【空头/反方】红队。现在的命题是：{topic}\n多头的观点是：\n{proponent_arg}\n请运用芒格反向思维和墨菲定律，极力挑刺，寻找泡沫、黑天鹅和崩盘风险。驳斥多头的逻辑，列出核心的3-5个致命风险点。"
    opp_response = client.models.generate_content(
        model='gemini-3.5-flash-lite',
        contents=opponent_prompt,
        config=types.GenerateContentConfig(temperature=0.7)
    )
    opponent_arg = opp_response.text

    # Judge
    judge_prompt = f"你是一个法庭辩论中的【中立集成法官】。现在的命题是：{topic}\n\n多头观点：\n{proponent_arg}\n\n空头观点：\n{opponent_arg}\n\n请不要偏袒任何一方。你的任务是：\n1. 提炼双方的共识与根本分歧。\n2. 输出一个复用/防御矩阵（在什么条件下多头成立，在什么条件下空头成立）。\n3. 给出最终的行动建议（Actionable Advice）。"
    judge_response = client.models.generate_content(
        model='gemini-3.5-flash-lite',
        contents=judge_prompt,
        config=types.GenerateContentConfig(temperature=0.3)
    )
    judge_arg = judge_response.text
    
    full_markdown = f"# ⚖️ 决策沙盘：{topic}\n\n## 📈 多头 (Proponent)\n{proponent_arg}\n\n## 📉 空头 (Opponent)\n{opponent_arg}\n\n## 👨‍⚖️ 法官裁决 (Judge)\n{judge_arg}"
    
    return full_markdown, judge_arg

async def court_agent_debate(topic: str):
    return await asyncio.to_thread(_sync_court_agent_debate, topic)

async def handle_court(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic = " ".join(context.args)
    if not topic:
        await update.message.reply_text("⚖️ 请在命令后加上你要评估的决策命题。例如：`/court 当前是否应该清仓美股科技股？`", parse_mode="Markdown")
        return
        
    status_msg = await update.message.reply_text("⚖️ *法庭已开庭*...\n\n🔍 正在传唤多头、空头与法官，大语言模型正在激烈辩论中，请稍候约10-20秒...", parse_mode="Markdown")
    
    try:
        full_md, judge_summary = await court_agent_debate(topic)
        
        # Save to local Obsidian
        os.makedirs(COURT_ARCHIVE_DIR, exist_ok=True)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
        
        # Sanitize topic for filename
        safe_topic = "".join([c for c in topic[:20] if c.isalpha() or c.isdigit() or c=='\u4e00' <= c <= '\u9fff']).rstrip()
        if not safe_topic:
            safe_topic = "Topic"
        filename = f"法庭决策_{safe_topic}_{timestamp}.md"
        filepath = os.path.join(COURT_ARCHIVE_DIR, filename)
        
        frontmatter = f"---\n创建时间: {date_str}\n标签: #决策沙盘 #红蓝对抗 #多Agent\n---\n"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + full_md)
            
        logger.info(f"Court debate saved to {filepath}")
        
        # Send summary to telegram
        telegram_reply = f"⚖️ *决策沙盘法庭：* {topic}\n\n*👨‍⚖️ 法官判决总结：*\n{judge_summary}\n\n_✅ 完整辩论记录已保存至 Obsidian ({filename})_"
        
        # Telegram has a 4096 char limit
        if len(telegram_reply) > 4000:
            telegram_reply = telegram_reply[:4000] + "...\n(截断)"
            
        await status_msg.edit_text(telegram_reply, parse_mode=None) # parse_mode=None because Gemini output might have unescaped markdown breaking Telegram's MarkdownV2
        
    except Exception as e:
        logger.error(f"Court logic failed: {e}")
        await status_msg.edit_text(f"❌ 法庭辩论发生错误: {e}")

def main():
    logger.info("🤖 Starting Cognitive Debugger (Socrates) Telegram Bot...")
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
    application.add_handler(CommandHandler("court", handle_court))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
