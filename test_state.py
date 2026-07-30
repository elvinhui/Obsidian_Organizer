import os
from google import genai
from config import GEMINI_API_KEY
import time

client = genai.Client(api_key=GEMINI_API_KEY)

# write a dummy file
with open("test.txt", "w") as f:
    f.write("hello")
    
f = client.files.upload(file="test.txt")
print("State:", f.state, type(f.state))
if hasattr(f.state, "name"):
    print("State name:", f.state.name)

client.files.delete(name=f.name)
os.remove("test.txt")
