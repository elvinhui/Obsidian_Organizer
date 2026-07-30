import json
import logging
import typing_extensions as typing
from google import genai
from google.genai import types
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Configure Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Define the expected JSON structure
class SkillSchema(typing.TypedDict):
    category: str
    title: str
    tags: list[str]
    core_concepts: str
    action_sop: str
    connections: str

def generate_structured_json(raw_text: str, context_tag: str = "") -> dict:
    """
    Uses Gemini API to extract and structure the knowledge from the raw text.
    Returns a dictionary matching the SkillSchema.
    """
    logger.info("Calling Gemini API to structure content...")
    
    prompt = f"""
    You are an expert Personal Knowledge Manager. Your task is to process the following raw text 
    and distill it into a highly structured knowledge card. Remove all fluff and focus on actionable, 
    insightful information.

    Context Tag: {context_tag} (Use this to help categorize the knowledge if relevant).
    
    Guidelines:
    1. 'category': Must be one of ["财商知识", "认知提升", "AI技术", "自动化构想", "硬技能开发", "财富优化", "奇思妙想"]. Pick the best fit.
    2. 'title': A concise, impactful title (Core concept + Specific scenario).
    3. 'tags': A list of relevant tags (e.g., ["#AI", "#Python"]).
    4. 'core_concepts': A one-sentence summary of the core insight.
    5. 'action_sop': Bulleted list of actionable steps. How can this be applied? What is the SOP?
    6. 'connections': Bulleted list of related ideas, potential blind spots, or reflections.

    Raw Text to process:
    --------------------
    {raw_text}
    """
    
    # Generate content with structured JSON enforcement and retry logic
    import time
    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SkillSchema,
                    temperature=0.2 # Lower temperature for more consistent formatting
                )
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
        raise Exception("Max retries exceeded for Gemini API structuring call.")
        
    try:
        # Gemini returns the JSON as text, we parse it
        result = json.loads(response.text)
        return result
    except Exception as e:
        logger.error(f"Failed to parse JSON from Gemini: {e}\nResponse text: {response.text}")
        raise ValueError("Invalid JSON returned by Gemini API")
