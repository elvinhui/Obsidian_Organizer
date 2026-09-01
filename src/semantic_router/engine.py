import os
import jinja2
from google import genai
from dotenv import load_dotenv

def render_prompt(filepath, user_input):
    if not os.path.isabs(filepath):
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # strip frontmatter
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            content = content[end+3:].strip()
            
    template = jinja2.Template(content)
    return template.render(user_input=user_input)

def execute_prompt(prompt_text, api_key=None):
    if not api_key:
        load_dotenv()
        if not os.getenv("GEMINI_API_KEY"):
            load_dotenv("lightsail_bot/.env")
        api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt_text
    )
    return response.text
