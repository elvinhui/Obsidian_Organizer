import os
import re
import uuid
import tempfile
import logging
import requests
import urllib.request
import fitz  # PyMuPDF
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
from google import genai

from config import JINA_API_KEY, GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

# Configure Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

def extract_webpage(url: str) -> str:
    """Uses Jina Reader API to extract text from a webpage."""
    logger.info(f"Extracting webpage via Jina Reader: {url}")
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}"
    } if JINA_API_KEY else {}
    
    jina_url = f"https://r.jina.ai/{url}"
    response = requests.get(jina_url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

def extract_youtube(url: str) -> str:
    """Uses youtube-transcript-api to extract subtitles."""
    logger.info(f"Extracting YouTube subtitles: {url}")
    
    # Extract video ID
    video_id = None
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "youtube.com/watch" in url:
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0]

    if not video_id:
        raise ValueError(f"Could not extract YouTube video ID from URL: {url}")

    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    
    # Try fetching Chinese first, then fallback to English
    transcript = None
    try:
        transcript = transcript_list.find_transcript(['zh-Hans', 'zh-Hant', 'zh'])
    except:
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            # Fallback to the first available transcript if neither Chinese nor English is available
            transcript = list(transcript_list)[0]

    if not transcript:
        raise ValueError(f"No transcript found for video: {video_id}")
        
    transcript_data = transcript.fetch()
    text = " ".join([t['text'] for t in transcript_data])
    return text

def resolve_douyin_url(url: str) -> str:
    """Resolve Douyin short URLs to their standard web URL to avoid yt-dlp 'iesdouyin' errors."""
    if 'v.douyin.com' in url or 'iesdouyin.com' in url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req)
            final_url = res.geturl()
            # Try to extract the video ID
            match = re.search(r'video/(\d+)', final_url)
            if match:
                video_id = match.group(1)
                return f"https://www.douyin.com/video/{video_id}"
        except Exception as e:
            logger.warning(f"Failed to manually resolve Douyin URL: {e}")
    return url

def get_ffmpeg_location():
    """Finds ffmpeg installation directory dynamically."""
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)
        
    local_appdata = os.getenv("LOCALAPPDATA", "")
    if local_appdata:
        winget_pkg = os.path.join(local_appdata, "Microsoft", "WinGet", "Packages")
        if os.path.exists(winget_pkg):
            for root, dirs, files in os.walk(winget_pkg):
                if "ffmpeg.exe" in files:
                    return root
    return None

def extract_short_video(url: str) -> str:
    """
    Downloads audio using yt-dlp and uses Gemini to transcribe it.
    """
    logger.info(f"Extracting audio/transcription from short video: {url}")
    
    url = resolve_douyin_url(url)
    
    # Create temp directory
    temp_dir = tempfile.gettempdir()
    temp_file_id = str(uuid.uuid4())
    
    # yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '32',
        }],
        'postprocessor_args': {
            'ffmpeg': ['-ac', '1', '-ar', '16000']
        },
        'outtmpl': os.path.join(temp_dir, f"{temp_file_id}.%(ext)s"),
        'cookiefile': os.path.join(os.path.dirname(__file__), 'cookies.txt'),
        'quiet': True,
        'no_warnings': True,
        'noprogress': True
    }

    ffmpeg_dir = get_ffmpeg_location()
    if ffmpeg_dir:
        ydl_opts['ffmpeg_location'] = ffmpeg_dir
        logger.info(f"Using FFmpeg from: {ffmpeg_dir}")

    audio_path = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            raw_path = ydl.prepare_filename(info)
            base_path = os.path.splitext(raw_path)[0]
            
            # Postprocessor converts file to .m4a or .mp3, so check those extensions
            if os.path.exists(f"{base_path}.m4a"):
                audio_path = f"{base_path}.m4a"
            elif os.path.exists(f"{base_path}.mp3"):
                audio_path = f"{base_path}.mp3"
            else:
                audio_path = raw_path
            
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file was not created: {audio_path}")
            
        if os.path.getsize(audio_path) < 1024:
            raise Exception(f"Extracted audio file is too small or empty (yt-dlp likely failed due to cookies/login). Path: {audio_path}")

            
        import time
        if GROQ_API_KEY:
            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            if file_size_mb > 24.5:
                logger.warning(f"Audio file is {file_size_mb:.1f}MB, exceeding Groq's 25MB limit. Falling back to Gemini directly.")
            else:
                logger.info("GROQ_API_KEY found, using Groq Whisper API for ultra-fast transcription...")
                import groq
                groq_client = groq.Groq(api_key=GROQ_API_KEY)
                
                try:
                    with open(audio_path, "rb") as file:
                        transcription = groq_client.audio.transcriptions.create(
                            file=(os.path.basename(audio_path), file.read()),
                            model="whisper-large-v3",
                            prompt="这是一段中文语音内容，包含演讲、播客或对话，请准确转录：",
                            response_format="text",
                            language="zh"
                        )
                    if not transcription:
                        raise ValueError("Groq returned empty transcription.")
                    return transcription
                except Exception as e:
                    logger.warning(f"Groq transcription failed: {e}. Falling back to Gemini...")
                    # Fallback to Gemini if Groq fails
        
        logger.info(f"Uploading audio to Gemini for transcription...")
        audio_file = client.files.upload(file=audio_path)
        
        while audio_file.state.name == "PROCESSING":
            logger.info("Waiting for file to be processed by Gemini...")
            time.sleep(3)
            audio_file = client.files.get(name=audio_file.name)
            
        if audio_file.state.name == "FAILED":
            raise Exception(f"File processing failed on Gemini servers for {audio_path}")
        
        # We only want the transcription for now (we'll structure it later)
        prompt = "Please transcribe the audio into text exactly as spoken. If there are multiple speakers, just transcribe the content. Do not summarize, just provide the full transcript."
        
        max_retries = 5
        response = None
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=[audio_file, prompt]
                )
                break
            except Exception as e:
                err_str = str(e)
                if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"]):
                    delay = (2 ** attempt) * 15 # 15, 30, 60, 120, 240
                    logger.warning(f"Gemini API limit hit. Retrying in {delay}s (Attempt {attempt+1}/{max_retries}). Error: {err_str}")
                    time.sleep(delay)
                else:
                    raise
                    
        if not response:
            raise Exception("Max retries exceeded for Gemini API transcription call.")
            
        
        # Delete file from Gemini storage
        try:
            client.files.delete(name=audio_file.name)
        except Exception as e:
            logger.warning(f"Failed to delete remote Gemini file: {e}")
            
        if response and response.text:
            return response.text
        else:
            raise ValueError("Gemini returned empty or blocked transcription response.")
        
    finally:
        # Cleanup local file
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

def extract_xiaoyuzhou(url: str) -> str:
    """Extracts audio from Xiaoyuzhou FM and transcribes it via Gemini."""
    logger.info(f"Extracting Xiaoyuzhou podcast: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # 1. Fetch HTML
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    html = response.text
    
    # 2. Extract audio URL from meta tag
    match = re.search(r'<meta\s+property="og:audio"\s+content="([^"]+)"', html)
    if not match:
        raise ValueError("Could not find audio URL in Xiaoyuzhou page.")
        
    audio_url = match.group(1)
    logger.info(f"Found Xiaoyuzhou audio URL: {audio_url}")
    
    # 3. Download audio locally
    temp_dir = tempfile.gettempdir()
    temp_file_id = str(uuid.uuid4())
    ext = audio_url.split("?")[0].split(".")[-1]
    if ext not in ["mp3", "m4a", "wav", "aac"]:
        ext = "m4a"
        
    audio_path = os.path.join(temp_dir, f"xiaoyuzhou_{temp_file_id}.{ext}")
    
    try:
        logger.info(f"Downloading audio to {audio_path}...")
        with requests.get(audio_url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(audio_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        # 4. Upload and transcribe via Gemini
        import time
        logger.info("Uploading Xiaoyuzhou audio to Gemini for transcription...")
        audio_file = client.files.upload(file=audio_path)
        
        while audio_file.state.name == "PROCESSING":
            logger.info("Waiting for file to be processed by Gemini...")
            time.sleep(3)
            audio_file = client.files.get(name=audio_file.name)
            
        if audio_file.state.name == "FAILED":
            raise Exception(f"File processing failed on Gemini servers for {audio_path}")
            
        prompt = "Please transcribe this podcast audio into text exactly as spoken. If there are multiple speakers, just transcribe the content. Do not summarize, just provide the full transcript."
        
        max_retries = 5
        response = None
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model='gemini-3.5-flash-lite',
                    contents=[audio_file, prompt]
                )
                break
            except Exception as e:
                err_str = str(e)
                if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"]):
                    delay = (2 ** attempt) * 15
                    logger.warning(f"Gemini API limit hit. Retrying in {delay}s (Attempt {attempt+1}/{max_retries}). Error: {err_str}")
                    time.sleep(delay)
                else:
                    raise
                    
        if not response:
            raise Exception("Max retries exceeded for Gemini API transcription call.")
            
        # Delete file from Gemini storage
        client.files.delete(name=audio_file.name)
        
        return response.text
        
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

def extract_local_doc(path: str) -> str:
    """Uses PyMuPDF to extract text from a local PDF."""
    logger.info(f"Extracting local document: {path}")
    
    # Handle obsidian wiki links like [[path/to/file.pdf]]
    clean_path = path.replace("[[", "").replace("]]", "").strip()
    
    # If it's not absolute, we might need to resolve it against the vault root,
    # but for simplicity, let's assume the user provides a valid relative/absolute path
    
    if not os.path.exists(clean_path):
        raise FileNotFoundError(f"Local document not found: {clean_path}")
        
    text = ""
    if clean_path.lower().endswith(".pdf"):
        doc = fitz.open(clean_path)
        for page in doc:
            text += page.get_text()
    else:
        # Fallback to plain text reading if not pdf (e.g. word docs need python-docx, can be added later)
        with open(clean_path, "r", encoding="utf-8") as f:
            text = f.read()
            
    return text

def process_url_or_path(payload: str) -> str:
    """Main routing function for extraction."""
    payload = payload.strip()
    
    # Try to find a URL in the payload
    url_match = re.search(r'(https?://[^\s]+)', payload)
    target = url_match.group(1) if url_match else payload
    
    # YouTube
    if "youtube.com" in target or "youtu.be" in target:
        return extract_youtube(target)
        
    # Xiaoyuzhou
    elif "xiaoyuzhoufm.com" in target:
        return extract_xiaoyuzhou(target)
        
    # Douyin / Bilibili / other video links supported by yt-dlp
    elif "douyin.com" in target or "bilibili.com" in target or "v.douyin.com" in target or "b23.tv" in target:
        return extract_short_video(target)
        
    # Normal Web URLs
    elif target.startswith("http://") or target.startswith("https://"):
        return extract_webpage(target)
        
    # Local files (Obsidian links)
    elif target.startswith("[[") or target.endswith(".pdf"):
        return extract_local_doc(target)
        
    # Fallback: assume it's just raw text provided by user
    else:
        return target
