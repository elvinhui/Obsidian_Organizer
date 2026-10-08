import os
import zlib
import base64

AUTH_DATA_B64 = (
    "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"
    "fqqr/xBc/vX8oD0mcFJefN3765VdX3eDy"
)

def setup_auth():
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lightsail_bot"))
    os.makedirs(target_dir, exist_ok=True)
    target_file = os.path.join(target_dir, "douyin_auth.json")
    
    decompressed = zlib.decompress(base64.b64decode(AUTH_DATA_B64))
    with open(target_file, "wb") as f:
        f.write(decompressed)
        
    print(f"[OK] Auth state successfully written to: {target_file}")
    print(f"File size: {os.path.getsize(target_file)} bytes")

if __name__ == "__main__":
    setup_auth()
