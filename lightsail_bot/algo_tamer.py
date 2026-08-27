import asyncio
import logging
import random
import os
import json
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
            logger.error("TELEGRAM_BOT_TOKEN not found in .env")
            return
            
        current_dir = os.path.dirname(os.path.abspath(__file__))
        chat_id_file = os.path.join(current_dir, "registered_users.json")
        if not os.path.exists(chat_id_file):
            logger.error("registered_users.json not found")
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
            resp = requests.post(url, files=files, data=data)
            if resp.status_code == 200:
                logger.info(f"📤 截图已成功发送至 Telegram!")
            else:
                logger.error(f"发送 Telegram 截图失败: {resp.text}")
    except Exception as e:
        logger.error(f"发送 Telegram 截图时发生错误: {e}")

async def tame_algorithm(keywords, auth_file="douyin_auth.json"):
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
                
                video_selectors = [
                    'a[href*="/video/"]',
                    'a[href*="/discover/"]',
                    'li a img',
                    'div[data-e2e="search-video-card"]'
                ]
                
                found = False
                for selector in video_selectors:
                    try:
                        videos = await page.query_selector_all(selector)
                        for v in videos:
                            logger.info(f"🖱️ 匹配到视频 ({selector})，模拟点击进入...")
                            await v.click()
                            found = True
                            break
                        if found:
                            break
                    except Exception:
                        continue
                
                if found:
                    watch_time = random.randint(15000, 25000)
                    logger.info(f"📺 静默播放中，强制停留 {watch_time/1000} 秒以拉满推荐权重...")
                    await page.wait_for_timeout(watch_time)
                else:
                    logger.warning("⚠️ 未找到匹配的视频容器。尝试保存截图并发给主人...")
                    err_pic = f"douyin_error_{keyword}.png"
                    await page.screenshot(path=err_pic)
                    # 发送到 Telegram
                    send_telegram_photo(err_pic, caption=f"⚠️ 抖音找不到搜索结果或被拦截了\n关键词: {keyword}")
            
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
    test_keywords = ["系统思维", "认知觉醒", "纳瓦尔宝典", "控制二分法"]
    current_dir = os.path.dirname(os.path.abspath(__file__))
    auth_file_path = os.path.join(current_dir, "douyin_auth.json")
    asyncio.run(tame_algorithm(test_keywords, auth_file=auth_file_path))
