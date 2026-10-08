import asyncio
import logging
import os
import random
from typing import Dict, Any, List, Optional, Callable
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from src.douyin_cleaner.db import (
    get_followings,
    update_following_status,
    DEFAULT_DB_PATH
)
from src.douyin_cleaner.scraper import find_auth_file
from src.douyin_cleaner.notifier import (
    build_cleanup_report,
    send_telegram_notification,
    send_telegram_photo
)

logger = logging.getLogger(__name__)

def aggregate_cleanup_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes aggregate execution counts from cleanup results."""
    total = len(results)
    success = sum(1 for r in results if r.get("status") == "deleted")
    error = sum(1 for r in results if r.get("status") != "deleted")
    canceled = sum(1 for r in results if r.get("is_canceled") and r.get("status") == "deleted")
    inactive = sum(1 for r in results if not r.get("is_canceled") and r.get("days_inactive", 0) >= 180 and r.get("status") == "deleted")
    
    return {
        "total_targets": total,
        "success_count": success,
        "error_count": error,
        "canceled_count": canceled,
        "inactive_count": inactive
    }

async def execute_clean_targets(
    db_path: str = DEFAULT_DB_PATH,
    target_sec_uids: Optional[List[str]] = None,
    auth_file: Optional[str] = None,
    headless: bool = True,
    notify_telegram: bool = True,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Dict[str, Any]:
    """
    Quietly unfollows targeted accounts in headless mode,
    protecting account with risk-control circuit breaking and Telegram notifications.
    """
    if not auth_file:
        auth_file = find_auth_file()
        
    if not auth_file or not os.path.exists(auth_file):
        raise FileNotFoundError("找不到身份凭证文件 (douyin_auth.json)。")

    # Determine targets
    if target_sec_uids:
        all_followings = get_followings(db_path)
        lookup = {u["sec_uid"]: u for u in all_followings}
        targets = [lookup[s] for s in target_sec_uids if s in lookup]
    else:
        targets = get_followings(db_path, audit_status="pending_delete")

    if not targets:
        logger.info("当前没有待清理的账号。")
        return aggregate_cleanup_summary([])

    total_targets = len(targets)
    logger.info(f"🚀 开始静默清理，目标账号总数: {total_targets}")
    results: List[Dict[str, Any]] = []

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

        for idx, u in enumerate(targets, 1):
            sec_uid = u["sec_uid"]
            nickname = u.get("nickname", "未知")
            url = f"https://www.douyin.com/user/{sec_uid}"
            
            if progress_callback:
                progress_callback(f"[{idx}/{total_targets}] 正在静默取关: {nickname}...", idx, total_targets)

            logger.info(f"进入用户主页: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(2500)
                
                # Check for risk control / captcha popups
                content = await page.content()
                if "验证码" in content or "验证后继续" in content or "操作过于频繁" in content:
                    logger.warning(f"⚠️ 检测到风控提示或验证码，触发安全熔断！")
                    screenshot_path = "douyin_captcha_breaker.png"
                    await page.screenshot(path=screenshot_path)
                    send_telegram_photo(screenshot_path, caption=f"⚠️ 抖音取关检测到风控或验证码，已自动安全熔断停止！\n账号: {nickname}")
                    results.append({
                        "sec_uid": sec_uid,
                        "status": "circuit_breaker",
                        "is_canceled": u.get("is_canceled", 0),
                        "days_inactive": u.get("days_inactive", 0)
                    })
                    break

                # Find the follow button (已关注 / 互相关注)
                follow_btn = await page.query_selector('button:has-text("已关注"), button:has-text("互相关注"), [data-e2e="user-info-follow-btn"]:has-text("已关注")')
                
                if not follow_btn:
                    # Check if already not following
                    not_followed = await page.query_selector('button:has-text("关注")')
                    if not_followed:
                        logger.info(f"该账号已处于未关注状态: {nickname}")
                        update_following_status(db_path, sec_uid, "deleted", "已处于未关注状态")
                        results.append({
                            "sec_uid": sec_uid,
                            "status": "deleted",
                            "is_canceled": u.get("is_canceled", 0),
                            "days_inactive": u.get("days_inactive", 0)
                        })
                        continue
                    else:
                        logger.warning(f"未找到关注按钮: {nickname}")
                        update_following_status(db_path, sec_uid, "error", "未找到关注按钮")
                        results.append({
                            "sec_uid": sec_uid,
                            "status": "error",
                            "is_canceled": u.get("is_canceled", 0),
                            "days_inactive": u.get("days_inactive", 0)
                        })
                        continue

                # Click unfollow
                await follow_btn.click()
                await page.wait_for_timeout(1500)

                # Confirm popup if dialog appears
                confirm_btn = await page.query_selector('button:has-text("确定不再关注"), button:has-text("不再关注"), button:has-text("确定"), button:has-text("确认")')
                if confirm_btn:
                    await confirm_btn.click()
                    await page.wait_for_timeout(1000)

                logger.info(f"✅ 成功取关: {nickname}")
                update_following_status(db_path, sec_uid, "deleted", "取关成功")
                results.append({
                    "sec_uid": sec_uid,
                    "status": "deleted",
                    "is_canceled": u.get("is_canceled", 0),
                    "days_inactive": u.get("days_inactive", 0)
                })

            except Exception as e:
                logger.error(f"处理用户 {nickname} 时出错: {e}")
                update_following_status(db_path, sec_uid, "error", f"错误: {e}")
                results.append({
                    "sec_uid": sec_uid,
                    "status": "error",
                    "is_canceled": u.get("is_canceled", 0),
                    "days_inactive": u.get("days_inactive", 0)
                })

            # Humanized delay between unfollow actions: 3.5s - 6.0s
            cooldown = random.uniform(3.5, 6.0)
            await asyncio.sleep(cooldown)

        await browser.close()

    summary = aggregate_cleanup_summary(results)
    logger.info(f"🎉 取关批次执行完毕: 目标 {summary['total_targets']}, 成功 {summary['success_count']}, 失败 {summary['error_count']}")
    
    # Send report to Telegram
    if notify_telegram:
        report_text = build_cleanup_report(summary)
        send_telegram_notification(report_text)

    return summary
