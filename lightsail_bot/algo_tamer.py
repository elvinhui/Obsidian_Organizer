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
        return

    from playwright_stealth import Stealth

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
                # 等待网络空闲可能不够，增加 domcontentloaded
                await page.goto(search_url, wait_until="domcontentloaded")
                
                # 给 JS 渲染搜索结果留出更充足的时间
                await page.wait_for_timeout(4000)
                
                # 尝试点击搜索结果中的第一个视频 (使用多种兼容的 CSS 选择器)
                # 抖音搜索结果经常变动，涵盖 <a> 包含 href="/video/"，或带有 <img> 封面图的容器
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
                    logger.warning("⚠️ 未找到匹配的视频容器，抖音页面结构可能已更改或出现了滑块。")
                    # 截图留存以供调试
                    await page.screenshot(path=f"douyin_error_{keyword}.png")
                    logger.info(f"📸 现场截图已保存至 douyin_error_{keyword}.png，您可以传回本地查看。")
            
            except Exception as e:
                logger.error(f"❌ 处理关键词 '{keyword}' 时发生错误: {e}")
                try:
                    await page.screenshot(path=f"douyin_error_{keyword}.png")
                    logger.info(f"📸 现场截图已保存至 douyin_error_{keyword}.png")
                except:
                    pass
            
            finally:
                # 修复: 必须先关闭 page，然后用 asyncio.sleep，而不能用已关闭的 page 去 wait_for_timeout
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
