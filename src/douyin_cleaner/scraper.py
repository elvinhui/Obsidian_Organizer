import asyncio
import logging
import os
import json
import random
from typing import Dict, Any, List, Optional, Tuple, Callable
from playwright.async_api import async_playwright, Response
from playwright_stealth import Stealth
from src.douyin_cleaner.db import batch_upsert_followings, DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

def find_auth_file() -> Optional[str]:
    """Finds the douyin_auth.json credential file across likely project locations."""
    candidate_paths = [
        os.path.join(os.getcwd(), "lightsail_bot", "douyin_auth.json"),
        os.path.join(os.getcwd(), "douyin_auth.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lightsail_bot", "douyin_auth.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lightsail_bot", "douyin_auth.json"),
    ]
    for p in candidate_paths:
        abs_p = os.path.abspath(p)
        if os.path.exists(abs_p):
            return abs_p
    return None

def parse_following_response_data(json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parses raw Douyin API JSON response and extracts normalized following user list."""
    if not isinstance(json_data, dict):
        return []
        
    followings = json_data.get("followings")
    if not isinstance(followings, list):
        return []
        
    results = []
    for item in followings:
        if not isinstance(item, dict):
            continue
            
        sec_uid = item.get("sec_uid")
        if not sec_uid:
            continue
            
        # Extract avatar url safely
        avatar = ""
        for avatar_key in ["avatar_thumb", "avatar_168x168", "avatar_300x300", "avatar_larger"]:
            avatar_obj = item.get(avatar_key)
            if isinstance(avatar_obj, dict) and avatar_obj.get("url_list"):
                avatar = avatar_obj["url_list"][0]
                break
            elif isinstance(avatar_obj, str):
                avatar = avatar_obj
                break
                
        results.append({
            "sec_uid": sec_uid,
            "uid": str(item.get("uid", "")),
            "short_id": str(item.get("short_id", "")),
            "nickname": str(item.get("nickname", "未知用户")),
            "signature": str(item.get("signature", "")),
            "avatar": avatar,
            "follower_status": item.get("follower_status", 0)
        })
        
    return results

async def scrape_following_list(
    db_path: str = DEFAULT_DB_PATH,
    auth_file: Optional[str] = None,
    max_scrolls: int = 50,
    headless: bool = True,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Tuple[int, int]:
    """
    Quietly scrapes user following list in headless mode by intercepting
    Douyin's internal API responses while smoothly scrolling the follow list.
    """
    if not auth_file:
        auth_file = find_auth_file()
        
    if not auth_file or not os.path.exists(auth_file):
        raise FileNotFoundError(f"找不到身份凭证文件 (douyin_auth.json)。请确保凭证已导出至 lightsail_bot 目录。")

    captured_items: Dict[str, Dict[str, Any]] = {}
    has_more_data = True

    async def handle_response(response: Response):
        nonlocal has_more_data
        url = response.url
        if "following/list" in url or "user/following" in url:
            try:
                data = await response.json()
                items = parse_following_response_data(data)
                for item in items:
                    captured_items[item["sec_uid"]] = item
                if items:
                    batch_upsert_followings(db_path, items)
                if isinstance(data, dict):
                    has_more_data = bool(data.get("has_more", 1))
                logger.info(f"拦截到关注列表数据: 捕获 {len(items)} 条，当前累计 {len(captured_items)} 条（已实时入库）")
                if progress_callback:
                    progress_callback(f"已捕获并入库 {len(captured_items)} 个关注账号...", len(captured_items))
            except Exception as e:
                logger.debug(f"解析 response 失败: {e}")

    logger.info("🚀 启动静默无头浏览器准备嗅探关注列表...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            storage_state=auth_file,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        page.on("response", handle_response)

        target_url = "https://www.douyin.com/user/self"
        logger.info(f"后台导航至个人主页: {target_url}")
        if progress_callback:
            progress_callback("正在加载个人主页...", 0)
            
        await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3500)

        # Click the following tab/element to open following modal
        logger.info("正在点击个人主页关注按钮以唤起关注弹窗...")
        if progress_callback:
            progress_callback("正在打开关注列表弹窗...", 0)

        follow_clicked = False
        try:
            btn = await page.wait_for_selector('[data-e2e="user-info-follow"]', timeout=8000)
            if btn:
                await btn.click()
                follow_clicked = True
        except Exception:
            pass

        if not follow_clicked:
            # Fallback search for elements starting with 关注
            candidates = await page.query_selector_all('span, div, p, a')
            for c in candidates:
                try:
                    txt = (await c.inner_text()).strip()
                    if txt.startswith('关注') and ('万' in txt or any(ch.isdigit() for ch in txt)):
                        await c.click()
                        follow_clicked = True
                        break
                except Exception:
                    continue

        await page.wait_for_timeout(2500)
        
        # Position mouse over following modal (center of screen)
        modal_x, modal_y = 500, 450
        try:
            await page.mouse.move(modal_x, modal_y)
        except Exception:
            pass

        last_count = 0
        no_growth_rounds = 0

        for scroll_idx in range(1, max_scrolls + 1):
            curr_count = len(captured_items)
            logger.info(f"第 {scroll_idx}/{max_scrolls} 次滚动，当前已捕获: {curr_count}")
            
            if curr_count > last_count:
                last_count = curr_count
                no_growth_rounds = 0
            else:
                no_growth_rounds += 1
                
            if no_growth_rounds >= 8 and not has_more_data:
                logger.info("连续未获取到新增数据且 has_more=0，滚动结束。")
                break
                
            # Scroll within the following list modal
            try:
                await page.mouse.wheel(0, 1200)
            except Exception:
                pass
                
            # Smooth delay between 0.8s and 1.5s
            delay = random.uniform(0.8, 1.5)
            await page.wait_for_timeout(int(delay * 1000))

        await browser.close()

    total_captured = len(captured_items)
    new_saved = batch_upsert_followings(db_path, list(captured_items.values()))
    logger.info(f"✅ 抓取完成！共捕获 {total_captured} 个关注账号，成功入库/更新 {new_saved} 条。")
    return total_captured, new_saved
