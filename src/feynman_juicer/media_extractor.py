import os
import yt_dlp
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

def _convert_json_to_netscape_cookies(raw_data, out_path: str) -> bool:
    """Converts JSON cookies list or Playwright auth dict into Netscape format, stripping login sessions."""
    cookies = raw_data if isinstance(raw_data, list) else raw_data.get("cookies", [])
    if not cookies:
        return False
    sensitive = {
        "sessionid", "sessionid_ss", "sid_guard", "sid_tt", "sid_ucp_v1", "ssid_ucp_v1",
        "uid_tt", "uid_tt_ss", "passport_assist_user", "passport_auth_mix_state",
        "login_time", "is_staff_user", "has_biz_token", "user_id"
    }
    lines = ["# Netscape HTTP Cookie File\n\n"]
    retained = 0
    for c in cookies:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "")
        if name in sensitive or any(name.startswith(p) for p in ["session", "passport", "sid_"]):
            continue
        domain = c.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        exp = c.get("expirationDate") or c.get("expires") or 0
        try:
            expiration = int(float(exp)) if exp and float(exp) > 0 else 0
        except Exception:
            expiration = 0
        value = c.get("value", "")
        lines.append(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
        retained += 1
    if retained > 0:
        with open(out_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    return False

def find_or_generate_cookies() -> Optional[str]:
    """Finds existing cookies.txt, converts JSON if needed, or generates from auth."""
    # 1. Check if cookies.txt or cookies_safe.txt already exists
    for txt_name in ["cookies_safe.txt", "cookies.txt"]:
        for base in [os.getcwd(), os.path.join(os.path.dirname(__file__), ".."), os.path.join(os.path.dirname(__file__), "..", "..")]:
            p = os.path.abspath(os.path.join(base, txt_name))
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().strip()
                    if content.startswith("[") or content.startswith("{"):
                        import json
                        parsed = json.loads(content)
                        out_netscape = os.path.join(os.getcwd(), "cookies.txt")
                        if _convert_json_to_netscape_cookies(parsed, out_netscape):
                            logger.info(f"Auto-converted JSON cookies from {p} to Netscape {out_netscape}")
                            return out_netscape
                    elif "# Netscape" in content or "\tdouyin.com" in content or "\t.douyin.com" in content:
                        return p
                except Exception as e:
                    logger.warning(f"Error checking cookie file {p}: {e}")

    # 2. Check for cookies.json / cookies_safe.json
    for json_name in ["cookies.json", "cookies_safe.json"]:
        for base in [os.getcwd(), os.path.join(os.path.dirname(__file__), ".."), os.path.join(os.path.dirname(__file__), "..", "..")]:
            p = os.path.abspath(os.path.join(base, json_name))
            if os.path.exists(p):
                try:
                    import json
                    with open(p, "r", encoding="utf-8") as f:
                        parsed = json.load(f)
                    out_netscape = os.path.join(os.getcwd(), "cookies.txt")
                    if _convert_json_to_netscape_cookies(parsed, out_netscape):
                        logger.info(f"Auto-converted JSON file {p} to Netscape {out_netscape}")
                        return out_netscape
                except Exception as e:
                    logger.warning(f"Error converting {p}: {e}")

    # 3. Check for douyin_auth.json
    for auth_p in [
        os.path.join(os.getcwd(), "lightsail_bot", "douyin_auth.json"),
        os.path.join(os.getcwd(), "douyin_auth.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lightsail_bot", "douyin_auth.json")
    ]:
        abs_auth = os.path.abspath(auth_p)
        if os.path.exists(abs_auth):
            try:
                import json
                with open(abs_auth, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                out_netscape = os.path.join(os.getcwd(), "cookies.txt")
                if _convert_json_to_netscape_cookies(parsed, out_netscape):
                    logger.info(f"Auto-generated Netscape cookies.txt from {abs_auth}")
                    return out_netscape
            except Exception as e:
                logger.warning(f"Failed to auto-generate cookies.txt from {abs_auth}: {e}")

    return None

def _should_retry_download(exc: Exception) -> bool:
    msg = str(exc)
    if "Fresh cookies" in msg or ("cookies" in msg.lower() and "needed" in msg):
        return False
    return True

class MediaExtractor:
    def __init__(self, output_dir="temp_audio"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(_should_retry_download))
    def download_audio(self, url: str) -> str:
        """
        使用 yt-dlp 下载并提取 32kbps 单声道 m4a 音频
        """
        logger.info(f"Starting audio extraction for URL: {url}")
        
        # 预处理重定向 (抖音短链接处理可以在这里扩展)
        if "v.douyin.com" in url:
            import requests
            try:
                resp = requests.head(url, allow_redirects=True, timeout=10)
                url = resp.url
                logger.info(f"Resolved Douyin short link to: {url}")
            except Exception as e:
                logger.warning(f"Failed to resolve short link: {e}")

        cookies_path = find_or_generate_cookies()

        ydl_opts = {
            'format': 'bestaudio/worst',  # 最低的音频质量即可满足转录
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '32',
            }],
            'postprocessor_args': [
                '-ac', '1', # 单声道缩小体积
            ],
            'outtmpl': os.path.join(self.output_dir, '%(extractor)s_%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': True,
        }
        
        if cookies_path and os.path.exists(cookies_path):
            ydl_opts['cookiefile'] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            # 根据 outtmpl 获取最终输出的文件路径
            ext = 'm4a'
            filename = f"{info_dict['extractor']}_{info_dict['id']}.{ext}"
            filepath = os.path.join(self.output_dir, filename)
            
            if os.path.exists(filepath):
                logger.info(f"Successfully extracted audio to: {filepath}")
                return filepath
            else:
                # 有些情况文件名可能不同，尝试从 info_dict 拿
                expected = ydl.prepare_filename(info_dict)
                # postprocessor 可能会把后缀改掉
                base, _ = os.path.splitext(expected)
                expected_m4a = base + '.m4a'
                if os.path.exists(expected_m4a):
                    return expected_m4a
                raise FileNotFoundError(f"Expected output file not found at {filepath}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    extractor = MediaExtractor()
    # Test URL
    # extractor.download_audio("https://v.douyin.com/idqX9W52/")
