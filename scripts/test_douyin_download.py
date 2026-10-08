import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.feynman_juicer.media_extractor import MediaExtractor

def main():
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://v.douyin.com/0ZoWBDTlCEg/"
    print(f"[TEST] Testing Douyin download for: {test_url}")
    extractor = MediaExtractor(output_dir="temp_audio")
    try:
        audio_path = extractor.download_audio(test_url)
        if audio_path and os.path.exists(audio_path):
            size = os.path.getsize(audio_path)
            print(f"[SUCCESS] Audio extracted successfully!")
            print(f"Path: {audio_path}")
            print(f"Size: {size} bytes ({size / 1024 / 1024:.2f} MB)")
            return 0
        else:
            print("[ERROR] Download finished but output file does not exist.")
            return 1
    except Exception as e:
        print(f"[FAIL] Download failed with error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
