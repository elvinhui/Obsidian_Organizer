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

def extract_douyin_audio_playwright(url: str, output_dir: str) -> Optional[str]:
    """
    Extracts Douyin audio directly via Playwright headless Chromium network interception.
    Runs headless browser, bypasses ArgusSecurityPlugin natively, and captures direct CDN audio stream.
    Zero cookies required, zero login credentials needed, 100% safe.
    """
    try:
        from playwright.sync_api import sync_playwright
        import requests
        import re

        os.makedirs(output_dir, exist_ok=True)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
        }

        # 1. Fast resolve short link without following cross-border redirect chain (0.3s)
        video_id = None
        if "v.douyin.com" in url:
            try:
                resp = requests.get(url, headers=headers, allow_redirects=False, timeout=5)
                location = resp.headers.get("Location") or resp.headers.get("location") or resp.url
                url = location
                logger.info(f"Resolved Douyin short link to: {url}")
            except Exception as e:
                logger.warning(f"Failed to resolve short link: {e}")

        match = re.search(r'video/(\d+)', url)
        if match:
            video_id = match.group(1)
            clean_url = f"https://www.douyin.com/video/{video_id}"
        else:
            video_id = "douyin_audio"
            clean_url = url

        audio_urls = []
        video_urls = []
        logger.info(f"🎭 Launching headless browser for Douyin clean URL: {clean_url}")

        with sync_playwright() as p:
            logger.info("Starting Chromium engine (Playwright)...")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--mute-audio',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--renderer-process-limit=1',
                    '--disable-extensions',
                    '--disable-background-networking',
                    '--disable-breakpad',
                    '--disable-component-update',
                    '--disable-features=Translate,OptimizationHints,MediaRouter',
                    '--js-flags=--max-old-space-size=96'
                ]
            )
            logger.info("Chromium engine started (low-RAM mode). Setting up browser context...")

            # Check if douyin_auth.json exists for authenticated bypass
            auth_file = None
            for auth_p in [
                os.path.join(os.getcwd(), "lightsail_bot", "douyin_auth.json"),
                os.path.join(os.getcwd(), "douyin_auth.json"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lightsail_bot", "douyin_auth.json")
            ]:
                if os.path.exists(auth_p):
                    auth_file = auth_p
                    break

            context_kwargs = {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
                'viewport': {'width': 1280, 'height': 800}
            }
            if auth_file:
                logger.info(f"Using browser auth state from: {auth_file}")
                context_kwargs['storage_state'] = auth_file

            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            def on_res(r):
                # Skip dummy player placeholders
                if 'uuu_265.mp4' in r.url:
                    return
                # Check for Douyin video detail API response (contains direct CDN links)
                if 'aweme/v1/web/aweme/detail' in r.url or 'web/detail' in r.url:
                    try:
                        detail_json = r.json()
                        aweme_detail = detail_json.get('aweme_detail', {})
                        # Extract full video stream URLs (guaranteed to contain full speech track)
                        v_urls = aweme_detail.get('video', {}).get('play_addr', {}).get('url_list', [])
                        if v_urls:
                            logger.info(f"Captured {len(v_urls)} direct video CDN URLs from detail API!")
                            video_urls.extend(v_urls)
                        m_urls = aweme_detail.get('music', {}).get('play_url', {}).get('url_list', [])
                        if m_urls:
                            audio_urls.extend(m_urls)
                    except Exception as e:
                        logger.debug(f"Detail JSON parse error: {e}")

                ct = r.headers.get('content-type', '')
                if 'media-audio' in r.url:
                    logger.info(f"Captured audio stream: {r.url[:80]}...")
                    audio_urls.append(r.url)
                elif (('audio' in ct or 'video' in ct) and any(k in r.url for k in ['tos-cn', 'douyinvod', 'zjcdn.com', 'bytevcloud'])) or r.request.resource_type == 'media':
                    logger.info(f"Captured media stream: {r.url[:80]}...")
                    video_urls.append(r.url)

            page.on('response', on_res)
            try:
                logger.info("Navigating to page (wait_until='commit')...")
                # Use wait_until='commit' so we don't block on heavy analytics or slow overseas assets
                page.goto(clean_url, wait_until='commit', timeout=20000)
                logger.info("Page committed. Listening for detail API & media streams (up to 75s)...")
                for i in range(75):
                    page.wait_for_timeout(1000)
                    if video_urls or audio_urls:
                        logger.info(f"Captured Douyin stream/API on second {i+1}!")
                        break
            except Exception as e:
                logger.warning(f"Playwright navigation warning: {e}")
            finally:
                logger.info("Closing browser...")
                browser.close()

        # Prioritize direct CDN URLs (no redirect, fastest throughput)
        cdn_video = [u for u in video_urls if any(k in u for k in ['zjcdn', 'tos-cn', 'douyinvod', 'bytevcloud'])]
        target_stream_url = cdn_video[0] if cdn_video else (video_urls[0] if video_urls else (audio_urls[0] if audio_urls else None))

        if not target_stream_url:
            logger.warning(f"No audio/video streams intercepted by Playwright for {clean_url}")
            return None

        out_file = os.path.join(output_dir, f"douyin_{video_id}.m4a")
        import shutil
        import subprocess
        ffmpeg_bin = shutil.which("ffmpeg")

        # 1. High-speed Direct FFmpeg HTTP Streaming Extraction
        # Avoids downloading large 100MB-700MB video files by using HTTP Range streaming
        if ffmpeg_bin:
            try:
                logger.info(f"🎧 Extracting audio directly via FFmpeg stream from CDN: {target_stream_url[:80]}...")
                cmd = [
                    ffmpeg_bin, "-y",
                    "-headers", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\nReferer: https://www.douyin.com/\r\n",
                    "-i", target_stream_url,
                    "-vn", "-acodec", "aac", "-b:a", "32k", "-ar", "16000",
                    out_file
                ]
                proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
                if proc.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
                    logger.info(f"✅ Successfully streamed Douyin audio ({os.path.getsize(out_file)} bytes) to {out_file}")
                    return out_file
                else:
                    logger.warning(f"FFmpeg stream extraction failed (code {proc.returncode}), falling back to file download")
            except Exception as e:
                logger.warning(f"FFmpeg stream failed ({e}), falling back to file download")

        # 2. Fallback: Download file chunk-by-chunk and convert
        temp_download = os.path.join(output_dir, f"temp_{video_id}.bin")
        logger.info(f"📥 Downloading intercepted Douyin stream to temporary file...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Referer': 'https://www.douyin.com/'
        }

        with requests.get(target_stream_url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            downloaded = 0
            with open(temp_download, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
            logger.info(f"Stream downloaded ({downloaded / 1024 / 1024:.2f} MB). Processing audio...")

        if ffmpeg_bin and os.path.exists(temp_download):
            try:
                cmd = [ffmpeg_bin, "-y", "-i", temp_download, "-vn", "-acodec", "aac", "-b:a", "32k", "-ar", "16000", out_file]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(temp_download):
                    os.remove(temp_download)
            except Exception as e:
                logger.warning(f"FFmpeg conversion failed ({e}), using raw stream as audio file")
                if os.path.exists(out_file):
                    os.remove(out_file)
                os.rename(temp_download, out_file)
        elif os.path.exists(temp_download):
            if os.path.exists(out_file):
                os.remove(out_file)
            os.rename(temp_download, out_file)

        if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
            logger.info(f"✅ Successfully downloaded Douyin audio ({os.path.getsize(out_file)} bytes) to {out_file}")
            return out_file

    except Exception as e:
        logger.warning(f"Playwright direct audio extraction failed: {e}")

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
        下载并提取音频。对于抖音视频，优先使用 Playwright 真实浏览器无损嗅探音频流（无需 Cookie 零风控），
        其他平台使用 yt-dlp 下载。
        """
        logger.info(f"Starting audio extraction for URL: {url}")

        # 1. 抖音直连嗅探：绕过 ArgusSecurityPlugin 和 Cookie 拦截
        if "douyin.com" in url or "v.douyin.com" in url:
            try:
                playwright_audio = extract_douyin_audio_playwright(url, self.output_dir)
                if playwright_audio:
                    return playwright_audio
            except Exception as e:
                logger.warning(f"Playwright Douyin direct extraction failed, falling back to yt-dlp: {e}")

        # 2. 预处理重定向 (抖音短链接处理可以在这里扩展)
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
