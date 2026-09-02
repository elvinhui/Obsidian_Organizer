import os
import yt_dlp
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class MediaExtractor:
    def __init__(self, output_dir="temp_audio"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
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

        ydl_opts = {
            'format': 'bestaudio/worst',  # 优先拿独立音频，没有就拿最差的视频
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '32',
            }],
            'postprocessor_args': [
                '-ac', '1', # 强制单声道，极致压缩
            ],
            'outtmpl': os.path.join(self.output_dir, '%(extractor)s_%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': True,
        }

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
