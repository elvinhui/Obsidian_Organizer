import asyncio
import logging
import random
import os
import sys
import datetime
import json
import glob
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

current_date = datetime.datetime.now().strftime('%Y-%m-%d')
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'algo_tamer_{current_date}.log')
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s', 
    handlers=[logging.FileHandler(log_file, encoding='utf-8'), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def get_target_chat_id(token=None):
    """
    Acquires target chat_id using multiple fallback strategies:
    1. Environment variable TELEGRAM_CHAT_ID or CHAT_ID
    2. Local registered_users.json
    3. Telegram API getUpdates (if available and not drained by active polling)
    """
    # 1. Environment variable
    env_chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    if env_chat_id:
        try:
            return int(str(env_chat_id).strip())
        except ValueError:
            pass

    current_dir = os.path.dirname(os.path.abspath(__file__))
    chat_id_file = os.path.join(current_dir, "registered_users.json")

    # 2. Local registered_users.json
    if os.path.exists(chat_id_file):
        try:
            with open(chat_id_file, "r", encoding="utf-8") as f:
                users = json.load(f)
                if users and isinstance(users, list) and len(users) > 0:
                    return users[0]
        except Exception as e:
            logger.warning(f"读取 registered_users.json 失败: {e}")

    # 3. getUpdates fallback
    if token:
        try:
            resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10).json()
            if resp.get("ok") and resp.get("result"):
                for update in reversed(resp["result"]):
                    msg = update.get("message") or update.get("callback_query", {}).get("message")
                    if msg and "chat" in msg:
                        found_id = msg["chat"]["id"]
                        try:
                            with open(chat_id_file, "w", encoding="utf-8") as f:
                                json.dump([found_id], f)
                        except Exception:
                            pass
                        return found_id
        except Exception as e:
            logger.debug(f"通过 getUpdates 获取 chat_id 失败: {e}")

    return None

def send_telegram_photo(photo_path, caption=""):
    try:
        load_dotenv()
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
            
        token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("SOCRATES_BOT_TOKEN")
        if not token:
            logger.error("未找到 Telegram Bot Token。")
            return
            
        chat_id = get_target_chat_id(token)
        if not chat_id:
            logger.error("未找到有效的 Telegram chat_id，跳过发送截图。可在 .env 中配置 TELEGRAM_CHAT_ID。")
            return
            
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, 'rb') as f:
            files = {'photo': f}
            # Use query params to ensure clean UTF-8 text without multipart encoding corruption
            params = {'chat_id': str(chat_id), 'caption': caption}
            requests.post(url, files=files, params=params, timeout=15)
    except Exception as e:
        logger.error(f"发送 Telegram 截图时发生错误: {e}")


def send_telegram_message(text):
    try:
        load_dotenv()
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
            
        token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("SOCRATES_BOT_TOKEN")
        if not token:
            logger.error("No Telegram token found.")
            return
            
        chat_id = get_target_chat_id(token)
        if not chat_id:
            logger.error("Could not find any registered chat_id to send the message. (请在 .env 中设置 TELEGRAM_CHAT_ID 或在 Telegram 中向 Bot 发送任意消息)")
            return
            
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {'chat_id': chat_id, 'text': text}
        requests.post(url, data=data, timeout=15)
    except Exception as e:
        logger.error(f"发送 Telegram 消息时发生错误: {e}")


def clean_title_to_keyword(title: str) -> str:
    """从 Obsidian 标题提取精简、高权重的核心概念用于抖音搜索"""
    import re
    # 去除系统标签如 [已合并]、书名号、特殊符号
    t = re.sub(r'\[.*?\]|\【.*?\】|#', '', title).strip()
    # 按冒号、横杠等拆分，提取主干主题词
    parts = re.split(r'[:：_\-—,，]', t)
    candidate = parts[0].strip() if parts else t
    if len(candidate) >= 3:
        t = candidate
    # 控制在 12 字以内，最符合抖音算法标签与搜索匹配
    return t[:12].strip()


def get_dynamic_keywords():
    """从 Obsidian 库中动态提取关键词（笔记标题）"""
    vault_paths = [
        r"G:\我的云端硬盘\Obsidian\Knowledge Base",
        r"/mnt/gdrive/Obsidian/Knowledge Base"
    ]
    
    vault_root = None
    for p in vault_paths:
        if os.path.exists(p):
            vault_root = p
            break
            
    fallback_keywords = ["系统思维", "认知觉醒", "纳瓦尔宝典", "控制二分法"]
    
    if not vault_root:
        logger.info("未找到 Obsidian 库，使用默认关键词。")
        return fallback_keywords
        
    # 优先从 Zeno_Keywords.md 读取 (如果用户手动建了这个文件)
    manual_file = os.path.join(vault_root, "Zeno_Keywords.md")
    if os.path.exists(manual_file):
        with open(manual_file, 'r', encoding='utf-8') as f:
            lines = [clean_title_to_keyword(line.replace('- ', '')) for line in f if line.strip() and not line.strip().startswith('#')]
            lines = [k for k in lines if k]
            if lines:
                logger.info("已从 Zeno_Keywords.md 加载自定义关键词列表。")
                return random.sample(lines, min(4, len(lines)))
    
    # 智能模式：从 "05 技能库" 中抽取笔记标题作为高级概念
    skills_dir = None
    for f in os.listdir(vault_root):
        if "05" in f or "Skill" in f or "技能库" in f:
            skills_dir = os.path.join(vault_root, f)
            break
            
    if skills_dir and os.path.isdir(skills_dir):
        md_files = glob.glob(os.path.join(skills_dir, "*.md"))
        if md_files:
            titles = [clean_title_to_keyword(os.path.basename(f).replace('.md', '')) for f in md_files]
            titles = [t for t in titles if t]
            sample_size = min(4, len(titles))
            chosen = random.sample(titles, sample_size)
            logger.info(f"🧠 智能提取: 已从您的技能库抽取今日知识点: {', '.join(chosen)}")
            return chosen
            
    return fallback_keywords

async def tame_algorithm_inner(auth_file="douyin_auth.json"):
    keywords = get_dynamic_keywords()
    
    if not os.path.exists(auth_file):
        logger.error(f"❌ 找不到身份凭证文件: {auth_file}")
        return

    try:
        from playwright_stealth import Stealth
    except ImportError:
        logger.error("缺少 playwright-stealth 模块，请确保在 venv 中安装了该模块。")
        return

    logger.info("🚀 启动算法反向驯化引擎 (Zeno-Flow) ...")
    
    async with async_playwright() as p:
        # Linux 512MB RAM nano VPS low-memory optimized flags
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--mute-audio",
                "--no-first-run",
                "--no-default-browser-check",
                "--renderer-process-limit=1",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-breakpad",
                "--disable-component-update",
                "--disable-features=Translate,OptimizationHints,MediaRouter",
                "--js-flags=--max-old-space-size=96"
            ]
        )
        
        context = await browser.new_context(
            storage_state=auth_file,
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
        )
        
        success_count = 0
        error_count = 0
        import urllib.parse
        for keyword in keywords:
            logger.info(f"\n🎯 [开始驯化] 正在向抖音注入优质关键词: {keyword}")
            page = await context.new_page()
            
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            
            try:
                encoded_kw = urllib.parse.quote(keyword)
                search_url = f"https://www.douyin.com/search/{encoded_kw}"
                logger.info(f"🌐 导航至搜索页: {search_url}")
                # Use wait_until="commit" so we don't stall on slow international analytics scripts
                await page.goto(search_url, wait_until="commit", timeout=30000)
                
                # Wait for search results to render
                try:
                    await page.wait_for_selector('a[href*="/video/"], [data-e2e="search-card"], div[class*="video"]', timeout=15000)
                except Exception:
                    await page.wait_for_timeout(4000)
                
                logger.info("🎯 寻找搜索结果中的首个视频...")
                video_link = await page.query_selector('a[href*="/video/"]')
                if video_link:
                    href = await video_link.get_attribute('href')
                    if href:
                        target_url = f"https://www.douyin.com{href}" if href.startswith('/') else href
                        logger.info(f"▶️ 直接进入视频: {target_url[:80]}...")
                        await page.goto(target_url, wait_until="commit", timeout=25000)
                        await page.wait_for_timeout(3000)
                    else:
                        await video_link.click()
                        await page.wait_for_timeout(3000)
                else:
                    logger.info("🖱️ 未找到明确链接，尝试点击卡片区域...")
                    await page.mouse.click(360, 420)
                    await page.wait_for_timeout(3000)
                
                watch_time = random.randint(15000, 25000)
                logger.info(f"📺 静默播放中，强制停留 {watch_time/1000} 秒以拉满推荐权重...")
                await page.wait_for_timeout(watch_time)
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"❌ 处理关键词 '{keyword}' 时发生错误: {e}")
                try:
                    err_pic = f"douyin_error_{keyword}.png"
                    await page.screenshot(path=err_pic)
                    send_telegram_photo(err_pic, caption=f"❌ 抖音脚本运行报错\n关键词: {keyword}\n错误: {e}")
                except Exception:
                    pass
            
            finally:
                await page.close()
                cooldown = random.randint(3, 7)
                await asyncio.sleep(cooldown)

        await browser.close()
        summary = f"✅ 今日算法反向驯化完成！\n关键词数量: {len(keywords)}\n成功: {success_count}\n失败: {error_count}\n您的推荐流已被清洗。"
        logger.info(summary)
        send_telegram_message(summary)

async def tame_algorithm(auth_file="douyin_auth.json"):
    try:
        await tame_algorithm_inner(auth_file)
    except Exception as e:
        logger.error(f"算法洗白脚本发生严重错误: {e}")
        send_telegram_message(f"❌ 算法洗白脚本发生严重错误:\n{e}")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    auth_file_path = os.path.join(current_dir, "douyin_auth.json")
    asyncio.run(tame_algorithm(auth_file=auth_file_path))
