import asyncio
import logging
import random
import os
import json
import glob
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
        logger.error(f"发送 Telegram 截图时发生错误: {e}")

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
            lines = [line.strip().replace('- ', '') for line in f if line.strip() and not line.strip().startswith('#')]
            if lines:
                logger.info(f"已从 Zeno_Keywords.md 加载自定义关键词列表。")
                return random.sample(lines, min(4, len(lines)))
    
    # 智能模式：从 "01 灵感库_Ideas" 中抽取笔记标题作为高级概念
    ideas_dir = None
    for f in os.listdir(vault_root):
        if "01" in f or "Ideas" in f or "灵感库" in f:
            ideas_dir = os.path.join(vault_root, f)
            break
            
    if ideas_dir and os.path.isdir(ideas_dir):
        md_files = glob.glob(os.path.join(ideas_dir, "*.md"))
        if md_files:
            titles = [os.path.basename(f).replace('.md', '') for f in md_files]
            sample_size = min(4, len(titles))
            chosen = random.sample(titles, sample_size)
            logger.info(f"🧠 智能提取: 已从您的灵感库抽取今日知识点: {', '.join(chosen)}")
            return chosen
            
    return fallback_keywords

async def tame_algorithm(auth_file="douyin_auth.json"):
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
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            storage_state=auth_file,
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        )
        
        for keyword in keywords:
            logger.info(f"\n🎯 [开始驯化] 正在向抖音注入优质关键词: {keyword}")
            page = await context.new_page()
            
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            
            try:
                search_url = f"https://www.douyin.com/search/{keyword}"
                await page.goto(search_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                
                logger.info(f"🖱️ 尝试通过绝对坐标点击第一个视频卡片...")
                await page.mouse.click(300, 450)
                await page.wait_for_timeout(3000)
                
                watch_time = random.randint(15000, 25000)
                logger.info(f"📺 静默播放中，强制停留 {watch_time/1000} 秒以拉满推荐权重...")
                await page.wait_for_timeout(watch_time)
                
            except Exception as e:
                logger.error(f"❌ 处理关键词 '{keyword}' 时发生错误: {e}")
                try:
                    err_pic = f"douyin_error_{keyword}.png"
                    await page.screenshot(path=err_pic)
                    send_telegram_photo(err_pic, caption=f"❌ 抖音脚本运行报错\n关键词: {keyword}\n错误: {e}")
                except:
                    pass
            
            finally:
                await page.close()
                cooldown = random.randint(3, 7)
                await asyncio.sleep(cooldown)

        await browser.close()
        logger.info("\n🎉 今日算法反向驯化完成！您的推荐流已被清洗。")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    auth_file_path = os.path.join(current_dir, "douyin_auth.json")
    asyncio.run(tame_algorithm(auth_file=auth_file_path))
