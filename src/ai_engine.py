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
    viewpoints_timestamps: str

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
    5. 'action_sop': 【核心铁律：严禁大而化之的哲学鸡汤与空洞口号！必须强制格式化为以下【If-Then 战备决策触发器】Markdown 格式】：
       - **🚨 IF（触发情境）**：明确客观的情绪/身体信号或具体外界场景（例如：“当坐在工位超过10分钟未开始并产生拖延念头时”、“当写完汇报准备提交前”，绝不能是空洞口号）。
       - **🎯 THEN（极简执行清单，严禁超过3步）**：
         - [ ] 1. 物理阻断/无脑微启动（<5秒，如离开工位倒杯水、敲下一行TODO注释）
         - [ ] 2. 核心操作动作（低阻力可执行具体步骤）
         - [ ] 3. 最小闭环交付（做完即停，不强求完美）
       - **🛑 ELSE（熔断底线）**：阻力过大或失控时的强制保护规则（例如：“立刻合上电脑离开工位散步15分钟，严禁坐在工位假装工作”）。
    6. 'connections': Bulleted list of related ideas, potential blind spots, or reflections.
    7. 'viewpoints_timestamps': If the raw text contains timestamps (like [MM:SS] or [HH:MM:SS]), extract a bulleted list of 5-10 key viewpoints/quotes with their exact timestamps (e.g., "- [12:34] Golden quote/viewpoint summary"). If no timestamps are present in the raw text, leave this field empty.

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
                model='gemini-3.5-flash',
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

def generate_deep_structured_json(raw_text: str, context_tag: str = "") -> dict:
    """
    Uses Gemini PRO model to deeply extract and structure knowledge from long-form text (e.g. podcasts).
    Utilizes JustStorm (multi-perspective expert) prompt.
    Returns a dictionary matching the SkillSchema.
    """
    logger.info(f"Calling Gemini PRO API for DEEP structuring (text length: {len(raw_text)})...")
    
    prompt = f"""
    You are a team of top-tier knowledge extraction experts operating under the 'JustStorm' framework. 
    Your goal is to deeply analyze the following long-form transcript (podcast/video) and extract dense, 
    highly valuable knowledge without losing critical details.
    
    Work together through these perspectives:
    1. The Philosopher: Identify anti-intuitive insights, compounding philosophies, and the fundamental 'Why'.
    2. The Architect: Translate insights into actionable systems, frameworks, and SOPs (Standard Operating Procedures).
    3. The Skeptic: Identify blind spots, opposing views, edge cases, and required prerequisites for the insights to work.
    
    Synthesize your findings into a single, highly structured knowledge card.

    Context Tag: {context_tag}
    
    Guidelines for the Output JSON:
    1. 'category': Must be one of ["财商知识", "认知提升", "AI技术", "自动化构想", "硬技能开发", "财富优化", "奇思妙想"]. Pick the best fit.
    2. 'title': A concise, impactful title (Core concept + Specific scenario).
    3. 'tags': A list of relevant tags (e.g., ["#DeepDive", "#PodcastInsight"]).
    4. 'core_concepts': A dense, comprehensive summary of the core insights (can be 2-3 sentences).
    5. 'action_sop': 【核心铁律：严禁大而化之的哲学鸡汤与空洞口号！必须强制格式化为以下【If-Then 战备决策触发器】Markdown 格式】：
       - **🚨 IF（触发情境）**：明确客观的情绪/身体信号或具体外界场景（例如：“当准备做实盘交易下单前”、“当写完文案准备发送前”）。
       - **🎯 THEN（极简执行清单，严禁超过3步）**：
         - [ ] 1. 物理阻断/无脑微启动（<5秒极低摩擦动作）
         - [ ] 2. 核心操作动作（低阻力可执行具体步骤）
         - [ ] 3. 最小闭环交付（做完即停，不强求完美）
       - **🛑 ELSE（熔断底线）**：阻力过大或出现冲动时的强制熔断机制（例如：“强制锁定30分钟，严禁冲动下单”）。
    6. 'connections': Bulleted list of related ideas, potential blind spots, and edge cases.
    7. 'viewpoints_timestamps': If the raw text contains timestamps (like [MM:SS] or [HH:MM:SS]), extract a dense bulleted list of 5-10 key viewpoints/quotes with their exact timestamps (e.g., "- [12:34] Golden quote/viewpoint summary"). If no timestamps are present in the raw text, leave this field empty.

    Raw Text to process:
    --------------------
    {raw_text}
    """
    
    import time
    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SkillSchema,
                    temperature=0.2
                )
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
        raise Exception("Max retries exceeded for Gemini API deep structuring call.")
        
    try:
        result = json.loads(response.text)
        return result
    except Exception as e:
        logger.error(f"Failed to parse JSON from Gemini: {e}\nResponse text: {response.text}")
        raise ValueError("Invalid JSON returned by Gemini API")

def generate_moc_structured_json(raw_text: str, context_tag: str = "") -> dict:
    """
    Map-Reduce architecture for extremely long content (e.g. 1-2 hour podcasts).
    Splits text into chunks, summarizes each chunk (Map), and synthesizes a MOC with subcards (Reduce).
    """
    logger.info(f"Starting Map-Reduce structuring for massive text (length: {len(raw_text)})...")
    
    # 1. Chunking (Split into roughly 8000 character chunks)
    chunk_size = 8000
    chunks = [raw_text[i:i+chunk_size] for i in range(0, len(raw_text), chunk_size)]
    logger.info(f"Split raw text into {len(chunks)} chunks for processing.")
    
    # 2. Map Phase
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {i+1}/{len(chunks)}...")
        prompt = f"""
        You are analyzing part {i+1} of a massive {len(chunks)}-part podcast/speech.
        Extract the most critical insights, facts, arguments, and actionable advice from this segment.
        Be extremely detailed. Do NOT write a short summary. Retain high information density.
        
        Text Segment:
        {chunk}
        """
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt
        )
        chunk_summaries.append(f"--- Chunk {i+1} Insights ---\n" + response.text)
        
    # 3. Reduce Phase
    combined_summaries = "\n\n".join(chunk_summaries)
    logger.info("Map phase complete. Starting Reduce phase to build MOC...")
    
    reduce_prompt = f"""
    You are an expert Personal Knowledge Manager. You are given a detailed summary of a massive podcast/speech.
    Your task is to synthesize this into a "Map of Content" (MOC) and several connected sub-topics.
    
    Context Tag: {context_tag}
    
    Guidelines:
    1. 'category': Must be one of ["财商知识", "认知提升", "AI技术", "自动化构想", "硬技能开发", "财富优化", "奇思妙想"].
    2. 'title': A concise, impactful title (Core concept).
    3. 'tags': A list of relevant tags (e.g., ["#Podcast", "#MOC"]).
    4. 'core_concepts': A comprehensive overview of the entire podcast's main thesis.
    5. 'action_sop': 【核心铁律：严禁哲学鸡汤，强制使用 If-Then 战备决策触发器格式】：
       - **🚨 IF（触发情境）**：明确客观的触发情境（身体/情绪信号或具体外界场景）
       - **🎯 THEN（极简执行清单，<3步）**：极简无脑启动与低阻力执行
       - **🛑 ELSE（熔断底线）**：阻力过大或失控时的强制保护规则
    6. 'connections': Bulleted list of the sub-topics that you extracted (to serve as an index).
    7. 'viewpoints_timestamps': If the raw text contains timestamps (like [MM:SS] or [HH:MM:SS]), extract a dense bulleted list of 5-10 key viewpoints/quotes with their exact timestamps (e.g., "- [12:34] Golden quote/viewpoint summary"). If no timestamps are present in the raw text, leave this field empty.
    
    Summaries:
    {combined_summaries}
    """
    
    import time
    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-pro',
                contents=reduce_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SkillSchema,
                    temperature=0.2
                )
            )
            break
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"]):
                delay = (2 ** attempt) * 15
                logger.warning(f"Gemini API limit hit in Reduce phase. Retrying in {delay}s. Error: {err_str}")
                time.sleep(delay)
            else:
                raise
                
    if not response:
        raise Exception("Max retries exceeded for Gemini API Reduce call.")
        
    try:
        result = json.loads(response.text)
        # Note: We return the SkillSchema structure which will act as the MOC card.
        # Future enhancement: The template_engine can generate multiple physical files.
        return result
    except Exception as e:
        logger.error(f"Failed to parse JSON from Gemini Reduce phase: {e}\nResponse text: {response.text}")
        raise ValueError("Invalid JSON returned by Gemini API")

