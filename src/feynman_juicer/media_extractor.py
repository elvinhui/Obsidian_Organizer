import os
import yt_dlp
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

def find_or_generate_cookies() -> Optional[str]:
    """Finds existing cookies.txt or auto-generates it from Playwright douyin_auth.json."""
    for p in [
        os.path.join(os.path.dirname(__file__), "..", "cookies.txt"),
        os.path.join(os.path.dirname(__file__), "..", "..", "cookies.txt"),
        os.path.join(os.getcwd(), "cookies.txt")
    ]:
        abs_p = os.path.abspath(p)
        if os.path.exists(abs_p):
            return abs_p

    for auth_p in [
        os.path.join(os.getcwd(), "lightsail_bot", "douyin_auth.json"),
        os.path.join(os.getcwd(), "douyin_auth.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lightsail_bot", "douyin_auth.json")
    ]:
        abs_auth = os.path.abspath(auth_p)
        if os.path.exists(abs_auth):
            try:
                import json
                with open(abs_auth, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                cookies = data.get('cookies', [])
                if cookies:
                    out_txt = os.path.join(os.getcwd(), "cookies.txt")
                    with open(out_txt, 'w', encoding='utf-8') as f:
                        f.write("# Netscape HTTP Cookie File\n\n")
                        for c in cookies:
                            domain = c.get('domain', '')
                            include_subdomains = 'TRUE' if domain.startswith('.') else 'FALSE'
                            path = c.get('path', '/')
                            secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                            expiration = int(c.get('expires', 0))
                            if expiration < 0:
                                expiration = 0
                            name = c.get('name', '')
                            value = c.get('value', '')
                            f.write(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
                    logger.info(f"Auto-generated Netscape cookies.txt from {abs_auth}")
                    return out_txt
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
