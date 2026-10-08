import asyncio
import logging
import os
import re
import random
import datetime
from typing import Dict, Any, Optional, Tuple, Callable, List
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from src.douyin_cleaner.db import (
    get_followings,
    update_audit_result,
    DEFAULT_DB_PATH
)
from src.douyin_cleaner.scraper import find_auth_file

logger = logging.getLogger(__name__)

CANCELED_KEYWORDS = [
    "该账号已注销",
    "用户已注销",
    "账号已注销",
    "账号已被重置",
    "账号已被封禁",
    "该用户已被封禁",
    "因违规已被封禁"
]

def detect_canceled_profile(html_text: str) -> bool:
    """Checks if the profile page contains hints of account cancellation or ban."""
    if not html_text:
        return False
    for kw in CANCELED_KEYWORDS:
        if kw in html_text:
            return True
    return False

def parse_relative_date(date_str: str, base_date: Optional[datetime.date] = None) -> Tuple[str, int]:
    """
    Parses date strings found on Douyin profiles into (normalized_date_str, days_inactive).
    Supports relative phrases (e.g. '3天前', '昨天', '1年前') and formats ('2024-05-12', '05-12').
    """
    if not base_date:
        base_date = datetime.date.today()

    raw = str(date_str).strip()
    
    # Check keywords
    if "刚刚" in raw or "小时前" in raw or "分钟前" in raw:
        return base_date.strftime("%Y-%m-%d"), 0
    if "昨天" in raw:
        d = base_date - datetime.timedelta(days=1)
        return d.strftime("%Y-%m-%d"), 1
    if "前天" in raw:
        d = base_date - datetime.timedelta(days=2)
        return d.strftime("%Y-%m-%d"), 2
        
    m_days = re.search(r"(\d+)\s*天前", raw)
    if m_days:
        num = int(m_days.group(1))
        d = base_date - datetime.timedelta(days=num)
        return d.strftime("%Y-%m-%d"), num
        
    m_weeks = re.search(r"(\d+)\s*周前", raw)
    if m_weeks:
        num = int(m_weeks.group(1)) * 7
        d = base_date - datetime.timedelta(days=num)
        return d.strftime("%Y-%m-%d"), num

    m_months = re.search(r"(\d+)\s*个?月前", raw)
    if m_months:
        num = int(m_months.group(1)) * 30
        d = base_date - datetime.timedelta(days=num)
        return d.strftime("%Y-%m-%d"), num

    m_years = re.search(r"(\d+)\s*年前", raw)
    if m_years:
        num = int(m_years.group(1)) * 365
        d = base_date - datetime.timedelta(days=num)
        return d.strftime("%Y-%m-%d"), num

    # Standard YYYY-MM-DD
    m_full = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", raw)
    if m_full:
        try:
            year, month, day = int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3))
            d = datetime.date(year, month, day)
            diff = (base_date - d).days
            return d.strftime("%Y-%m-%d"), max(0, diff)
        except ValueError:
            pass

    # MM-DD
    m_short = re.search(r"(\d{1,2})[-/.](\d{1,2})", raw)
    if m_short:
        try:
            month, day = int(m_short.group(1)), int(m_short.group(2))
            year = base_date.year
            d = datetime.date(year, month, day)
            if d > base_date: # From previous year
                d = datetime.date(year - 1, month, day)
            diff = (base_date - d).days
            return d.strftime("%Y-%m-%d"), max(0, diff)
        except ValueError:
            pass

    # Default fallback: unknown
    return "未知", 0

async def audit_user_profile(page, sec_uid: str) -> Dict[str, Any]:
    """Navigates quietly to user's profile and extracts audit indicators."""
    url = f"https://www.douyin.com/user/{sec_uid}"
    logger.info(f"正在后台审计主页: {url}")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1400)
    except Exception as e:
        logger.warning(f"访问主页超时或失败: {sec_uid}, error: {e}")
        return {
            "is_canceled": False,
            "last_publish_time": None,
            "days_inactive": 0,
            "is_private": False,
            "audit_note": f"访问失败: {e}"
        }

    content = await page.content()
    
    # 1. Canceled check
    if detect_canceled_profile(content):
        return {
            "is_canceled": True,
            "last_publish_time": None,
            "days_inactive": 9999,
            "is_private": False,
            "audit_note": "检测到账号已注销或重置"
        }

    # 2. Private or no works check
    if "该账号设置为私密" in content or "私密账号" in content:
        return {
            "is_canceled": False,
            "last_publish_time": None,
            "days_inactive": 0,
            "is_private": True,
            "audit_note": "私密账号"
        }
        
    if "暂无作品" in content or "作品 0" in content:
        return {
            "is_canceled": False,
            "last_publish_time": None,
            "days_inactive": 999,
            "is_private": False,
            "audit_note": "无发布任何作品"
        }

    # 3. Look for video publication date or post cards
    # Try finding video card elements or time spans
    date_candidates = []
    
    # Probe time-related tags
    time_elements = await page.query_selector_all("span, div, p")
    for el in time_elements[:50]: # limit check
        try:
            txt = (await el.inner_text()).strip()
            if any(k in txt for k in ["天前", "月前", "年前", "昨天", "前天"]) or re.search(r"\d{4}-\d{2}-\d{2}", txt) or re.search(r"^\d{2}-\d{2}$", txt):
                date_candidates.append(txt)
                if len(date_candidates) >= 3:
                    break
        except Exception:
            continue

    if date_candidates:
        best_date_str, days = parse_relative_date(date_candidates[0])
        note = f"最新作品: {best_date_str} (断更 {days} 天)"
        return {
            "is_canceled": False,
            "last_publish_time": best_date_str,
            "days_inactive": days,
            "is_private": False,
            "audit_note": note
        }

    return {
        "is_canceled": False,
        "last_publish_time": None,
        "days_inactive": 0,
        "is_private": False,
        "audit_note": "活跃或未检测到作品时间"
    }

async def audit_followings_batch(
    db_path: str = DEFAULT_DB_PATH,
    auth_file: Optional[str] = None,
    limit: int = 30,
    headless: bool = True,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> int:
    """
    Audits a batch of pending followings quietly in headless mode,
    updating the local database with inactivity and cancellation metrics.
    """
    if not auth_file:
        auth_file = find_auth_file()
        
    if not auth_file or not os.path.exists(auth_file):
        raise FileNotFoundError(f"找不到身份凭证文件 (douyin_auth.json)。")

    pending_users = get_followings(db_path, audit_status="pending", limit=limit)
    if not pending_users:
        logger.info("当前没有待审计的关注账号。")
        return 0

    logger.info(f"🚀 开始静默审计，本次待审计数量: {len(pending_users)}")
    total_count = len(pending_users)
    audited_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            storage_state=auth_file,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        for idx, u in enumerate(pending_users, 1):
            sec_uid = u["sec_uid"]
            nickname = u.get("nickname", "未知")
            
            # Fast-path for accounts explicitly named canceled
            if any(k in nickname for k in ["已注销", "账号已注销", "用户已注销"]):
                update_audit_result(
                    db_path=db_path,
                    sec_uid=sec_uid,
                    is_canceled=True,
                    last_publish_time=None,
                    days_inactive=9999,
                    is_private=False,
                    audit_note="昵称标记已注销"
                )
                audited_count += 1
                if progress_callback:
                    progress_callback(f"[{idx}/{total_count}] ⚡ 识别注销: {nickname}", idx, total_count)
                continue

            if progress_callback:
                progress_callback(f"[{idx}/{total_count}] 正在审计: {nickname}...", idx, total_count)
                
            audit_data = await audit_user_profile(page, sec_uid)
            update_audit_result(
                db_path=db_path,
                sec_uid=sec_uid,
                is_canceled=audit_data["is_canceled"],
                last_publish_time=audit_data["last_publish_time"],
                days_inactive=audit_data["days_inactive"],
                is_private=audit_data["is_private"],
                audit_note=audit_data["audit_note"]
            )
            audited_count += 1
            
            # Anti-detection jitter: 1.2s ~ 2.2s
            cooldown = random.uniform(1.2, 2.2)
            await asyncio.sleep(cooldown)

        await browser.close()

    logger.info(f"✅ 本批次审计完成！共处理 {audited_count} 个关注账号。")
    return audited_count
