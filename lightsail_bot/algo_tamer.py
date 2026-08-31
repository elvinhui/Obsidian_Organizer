import asyncio
import logging
import random
import os
import datetime
import json
import glob
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright

current_date = datetime.datetime.now().strftime('%Y-%m-%d')
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'algo_tamer_{current_date}.log')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(log_file, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

def send_telegram_photo(photo_path, caption=""):
    try:
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            return
            
        current_dir = os.path.dirname(os.path.abspath(__file__))
        chat_id_file = os.path.join(current_dir, "registered_users.json")
        if not os.path.exists(chat_id_file):
            return
            
        with open(chat_id_file, "r") as f:
            users = json.load(f)
            if not users:
                return
            chat_id = users[0]
            
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, 'rb') as f:
            files = {'photo': f}
            data = {'chat_id': chat_id, 'caption': caption}
            requests.post(url, files=files, data=data)
    except Exception as e:
        logger.error(f"å‘é€ Telegram æˆªå›¾æ—¶å‘ç”Ÿé”™è¯¯: {e}")


def send_telegram_message(text):
    try:
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            return
            
        current_dir = os.path.dirname(os.path.abspath(__file__))
        chat_id_file = os.path.join(current_dir, "registered_users.json")
        if not os.path.exists(chat_id_file):
            return
            
        with open(chat_id_file, "r") as f:
            users = json.load(f)
            if not users:
                return
            chat_id = users[0]
            
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {'chat_id': chat_id, 'text': text}
        requests.post(url, data=data)
    except Exception as e:
        logger.error(f"发送 Telegram 消息时发生错误: {e}")

def get_dynamic_keywords():
    """ä»Ž Obsidian åº“ä¸­åŠ¨æ€æå–å…³é”®è¯ï¼ˆç¬”è®°æ ‡é¢˜ï¼‰"""
    vault_paths = [
        r"G:\我的云端硬盘\Obsidian\Knowledge Base",
        r"/mnt/gdrive/Obsidian/Knowledge Base"
    ]
    
    vault_root = None
    for p in vault_paths:
        if os.path.exists(p):
            vault_root = p
            break
            
    fallback_keywords = ["ç³»ç»Ÿæ€ç»´", "è®¤çŸ¥è§‰é†’", "çº³ç“¦å°”å®å…¸", "æŽ§åˆ¶äºŒåˆ†æ³•"]
    
    if not vault_root:
        logger.info("æœªæ‰¾åˆ° Obsidian åº“ï¼Œä½¿ç”¨é»˜è®¤å…³é”®è¯ã€‚")
        return fallback_keywords
        
    # ä¼˜å…ˆä»Ž Zeno_Keywords.md è¯»å– (å¦‚æžœç”¨æˆ·æ‰‹åŠ¨å»ºäº†è¿™ä¸ªæ–‡ä»¶)
    manual_file = os.path.join(vault_root, "Zeno_Keywords.md")
    if os.path.exists(manual_file):
        with open(manual_file, 'r', encoding='utf-8') as f:
            lines = [line.strip().replace('- ', '') for line in f if line.strip() and not line.strip().startswith('#')]
            if lines:
                logger.info(f"å·²ä»Ž Zeno_Keywords.md åŠ è½½è‡ªå®šä¹‰å…³é”®è¯ åˆ—è¡¨ã€‚")
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
            titles = [os.path.basename(f).replace('.md', '') for f in md_files]
            sample_size = min(4, len(titles))
            chosen = random.sample(titles, sample_size)
            logger.info(f"🧠 智能提取: 已从您的技能库抽取今日知识点: {', '.join(chosen)}")
            return chosen
            
    return fallback_keywords

async def tame_algorithm_inner(auth_file="douyin_auth.json"):
    keywords = get_dynamic_keywords()
    
    if not os.path.exists(auth_file):
        logger.error(f"âŒ æ‰¾ä¸åˆ°èº«ä»½å‡­è¯æ–‡ä»¶: {auth_file}")
        return

    try:
        from playwright_stealth import Stealth
    except ImportError:
        logger.error("ç¼ºå°‘ playwright-stealth æ¨¡å—ï¼Œè¯·ç¡®ä¿åœ¨ venv ä¸­å®‰è£…äº†è¯¥æ¨¡å—ã€‚")
        return

    logger.info("ðŸš€ å¯åŠ¨ç®—æ³•åå‘é©¯åŒ–å¼•æ“Ž (Zeno-Flow) ...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            storage_state=auth_file,
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        )
        
        success_count = 0
        error_count = 0
        for keyword in keywords:
            logger.info(f"\nðŸŽ¯ [å¼€å§‹é©¯åŒ–] æ­£åœ¨å‘æŠ–éŸ³æ³¨å…¥ä¼˜è´¨å…³é”®è¯: {keyword}")
            page = await context.new_page()
            
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            
            try:
                search_url = f"https://www.douyin.com/search/{keyword}"
                await page.goto(search_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                
                logger.info(f"ðŸ–±ï¸ å°è¯•é€šè¿‡ç»å¯¹åæ ‡ç‚¹å‡»ç¬¬ä¸€ä¸ªè§†é¢‘å¡ç‰‡...")
                await page.mouse.click(300, 450)
                await page.wait_for_timeout(3000)
                
                watch_time = random.randint(15000, 25000)
                logger.info(f"ðŸ“º é™é»˜æ’­æ”¾ä¸­ï¼Œå¼ºåˆ¶åœç•™ {watch_time/1000} ç§’ä»¥æ‹‰æ»¡æŽ¨èæƒé‡...")
                await page.wait_for_timeout(watch_time)
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"âŒ å¤„ç†å…³é”®è¯ '{keyword}' æ—¶å‘ç”Ÿé”™è¯¯: {e}")
                try:
                    err_pic = f"douyin_error_{keyword}.png"
                    await page.screenshot(path=err_pic)
                    send_telegram_photo(err_pic, caption=f"âŒ æŠ–éŸ³è„šæœ¬è¿è¡ŒæŠ¥é”™\nå…³é”®è¯: {keyword}\né”™è¯¯: {e}")
                except:
                    pass
            
            finally:
                await page.close()
                cooldown = random.randint(3, 7)
                await asyncio.sleep(cooldown)

        await browser.close()
        summary = f"✅ 今日算法反向驯化完成！\n关键词数量: {len(keywords)}\n成功: {success_count}\n失败: {error_count}\n您的推荐流已被清洗。"
        logger.info(summary)
        send_telegram_message(summary)

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    auth_file_path = os.path.join(current_dir, "douyin_auth.json")
    # The global try-catch is now in tame_algorithm
    asyncio.run(tame_algorithm(auth_file=auth_file_path))

async def tame_algorithm(auth_file="douyin_auth.json"):
    try:
        await tame_algorithm_inner(auth_file)
    except Exception as e:
        logger.error(f"算法洗白脚本发生严重错误: {e}")
        send_telegram_message(f"❌ 算法洗白脚本发生严重错误:\n{e}")
