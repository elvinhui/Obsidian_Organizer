import asyncio
import logging
import random
import os
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def tame_algorithm(keywords, auth_file="douyin_auth.json"):
    if not os.path.exists(auth_file):
        logger.error(f"❌ 找不到身份凭证文件: {auth_file}")
        logger.info("请确保您已将本地生成的 douyin_auth.json 传输到了服务器的相同目录下。")
        return

    try:
        from playwright_stealth import stealth_async
    except ImportError:
        logger.error("缺少 playwright-stealth 模块，请运行: pip install playwright-stealth")
        return

    logger.info("🚀 启动算法反向驯化引擎 (Zeno-Flow) ...")
    
    async with async_playwright() as p:
        # 在服务器端，必须使用 headless=True
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # 加载您的专属“数字护照”
        context = await browser.new_context(
            storage_state=auth_file,
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        )
        
        for keyword in keywords:
            logger.info(f"\n🎯 [开始驯化] 正在向抖音注入优质关键词: {keyword}")
            page = await context.new_page()
            
            # 注入隐形斗篷，防止触发抖音的滑块验证码
            await stealth_async(page)
            
            try:
                search_url = f"https://www.douyin.com/search/{keyword}"
                await page.goto(search_url, wait_until="networkidle")
                
                # 随机停留，模拟人类看到搜索结果的反应时间
                delay = random.randint(2000, 4000)
                await page.wait_for_timeout(delay)
                
                # 寻找第一个有效视频链接
                video_selector = 'a[href*="/video/"]'
                await page.wait_for_selector(video_selector, timeout=10000)
                videos = await page.query_selector_all(video_selector)
                
                if videos:
                    # 模拟真实点击
                    for v in videos:
                        href = await v.get_attribute("href")
                        if href and "/video/" in href:
                            logger.info(f"🖱️ 找到目标视频，模拟点击进入...")
                            await v.click()
                            break
                    
                    # 最重要的一步：强制停留 15-25 秒。
                    # 推荐算法中“完播率”和“停留时长”的权重最高。
                    watch_time = random.randint(15000, 25000)
                    logger.info(f"📺 静默播放中，强制停留 {watch_time/1000} 秒以拉满推荐权重...")
                    await page.wait_for_timeout(watch_time)
                else:
                    logger.warning("⚠️ 未找到匹配的视频。")
            
            except Exception as e:
                logger.error(f"❌ 处理关键词 '{keyword}' 时发生错误 (可能是网络超时或遇到滑块): {e}")
            
            finally:
                await page.close()
                # 搜索下一个关键词前的安全冷却时间
                cooldown = random.randint(3000, 7000)
                await page.wait_for_timeout(cooldown)

        await browser.close()
        logger.info("\n🎉 今日算法反向驯化完成！您的推荐流已被清洗。")

if __name__ == "__main__":
    # 测试用的优质种子词汇
    test_keywords = ["系统思维", "认知觉醒", "纳瓦尔宝典", "控制二分法"]
    
    # 获取 auth 文件的绝对路径（假设和脚本在同一个目录）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    auth_file_path = os.path.join(current_dir, "douyin_auth.json")
    
    asyncio.run(tame_algorithm(test_keywords, auth_file=auth_file_path))
