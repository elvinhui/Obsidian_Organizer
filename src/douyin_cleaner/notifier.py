import os
import logging
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def load_telegram_config() -> tuple[Optional[str], Optional[int]]:
    """Loads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID with fallback search."""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        # Fallback to lightsail_bot/.env
        current_dir = os.path.dirname(os.path.abspath(__file__))
        lightsail_env = os.path.join(current_dir, "..", "..", "lightsail_bot", ".env")
        if os.path.exists(lightsail_env):
            load_dotenv(lightsail_env)
            token = token or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("SOCRATES_BOT_TOKEN")
            chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    int_chat_id = None
    if chat_id:
        try:
            int_chat_id = int(str(chat_id).strip().strip('"').strip("'"))
        except ValueError:
            pass

    return token, int_chat_id

def build_audit_report(stats: Dict[str, Any]) -> str:
    """Builds an audit summary report for Telegram."""
    total = stats.get("total", 0)
    audited = stats.get("audited", 0)
    canceled = stats.get("canceled", 0)
    inactive_180 = stats.get("inactive_180", 0)
    inactive_360 = stats.get("inactive_360", 0)
    pending = stats.get("pending", 0)
    
    report = (
        "🔍 **抖音关注列表审计完成！**\n\n"
        f"📊 **统计概览**：\n"
        f"- 总关注数: {total}\n"
        f"- 已完成审计: {audited}\n"
        f"- 待审计: {pending}\n\n"
        f"⚠️ **潜在清理目标**：\n"
        f"- 🪦 已注销账号: {canceled} 个\n"
        f"- 💤 超过半年未更新: {inactive_180} 个\n"
        f"- 🧊 超过一年未更新: {inactive_360} 个\n\n"
        "💡 *可在本地 Streamlit 面板中确认并一键清理。*"
    )
    return report

def build_cleanup_report(summary: Dict[str, Any]) -> str:
    """Builds a cleanup execution report for Telegram."""
    total = summary.get("total_targets", 0)
    success = summary.get("success_count", 0)
    error = summary.get("error_count", 0)
    canceled = summary.get("canceled_count", 0)
    inactive = summary.get("inactive_count", 0)
    
    report = (
        "🧹 **抖音关注列表清理战报！**\n\n"
        f"🎯 **清理目标总数**: {total}\n"
        f"✅ 成功取关: {success}\n"
        f"❌ 失败/跳过: {error}\n\n"
        f"📌 **分类明细**：\n"
        f"- 已注销账号: {canceled}\n"
        f"- 长期断更账号: {inactive}\n\n"
        "✨ *您的抖音关注流已被净化，推荐算法权重已重塑。*"
    )
    return report

def format_user_summary(users: List[Dict[str, Any]], limit: int = 10) -> str:
    """Formats a concise list of cleaned or audited users."""
    lines = []
    for u in users[:limit]:
        name = u.get("nickname", "未知")
        is_canceled = u.get("is_canceled", 0)
        days = u.get("days_inactive", 0)
        if is_canceled:
            lines.append(f"- 🪦 {name} (已注销)")
        else:
            lines.append(f"- 💤 {name} (断更 {days} 天)")
            
    if len(users) > limit:
        lines.append(f"... 等共 {len(users)} 人")
    return "\n".join(lines)

def send_telegram_notification(text: str) -> bool:
    """Sends a text message notification via Telegram Bot."""
    token, chat_id = load_telegram_config()
    if not token or not chat_id:
        logger.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info("Telegram notification sent successfully.")
            return True
        else:
            logger.error(f"Telegram send failed: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False

def send_telegram_photo(photo_path: str, caption: str = "") -> bool:
    """Sends a screenshot photo notification via Telegram Bot."""
    token, chat_id = load_telegram_config()
    if not token or not chat_id:
        logger.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": chat_id, "caption": caption}
            resp = requests.post(url, files=files, data=data, timeout=20)
            return resp.status_code == 200 and resp.json().get("ok")
    except Exception as e:
        logger.error(f"Error sending Telegram photo: {e}")
        return False
