import os
import re
import json
import shutil
import logging
import datetime
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, OPEN_QUESTIONS_DIR, INSIGHTS_DIR, ARCHIVES_DIR, WEEKLY_ROLLUP_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

def process_answered_questions():
    """
    Scans OPEN_QUESTIONS_DIR for any files where the user has provided an answer.
    Polishes the answer into an Insight, saves to INSIGHTS_DIR, and archives the original.
    """
    if not os.path.isdir(OPEN_QUESTIONS_DIR):
        return

    os.makedirs(INSIGHTS_DIR, exist_ok=True)
    os.makedirs(ARCHIVES_DIR, exist_ok=True)

    processed_count = 0

    for filename in os.listdir(OPEN_QUESTIONS_DIR):
        if not filename.endswith(".md"):
            continue
            
        filepath = os.path.join(OPEN_QUESTIONS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Check if the user has answered the question
            # We look for content after "> **一句话回答：**"
            answer_match = re.search(r'> \*\*一句话回答：\*\*(.*?)(?=## 🛠️|$)', content, re.DOTALL)
            reality_match = re.search(r'## 🛠️ 现实映射与论证 \(Reality Check\)(.*?)(?=## 👣|$)', content, re.DOTALL)
            
            if answer_match:
                answer_text = answer_match.group(1).strip()
                reality_text = reality_match.group(1).strip() if reality_match else ""
                
                # If there are meaningful characters (more than just bullet points or whitespace)
                clean_answer = re.sub(r'[\s\-*]', '', answer_text)
                if len(clean_answer) > 3:
                    # User answered! Let's process it.
                    logger.info(f"Detected answered question: {filename}")
                    
                    # Extract the original prompt
                    prompt_match = re.search(r'> \*\*当前思考的问题是：\*\*(.*?)(?=## 🎯|$)', content, re.DOTALL)
                    original_question = prompt_match.group(1).strip() if prompt_match else "未知问题"
                    
                    insight_title, insight_content = generate_insight_from_answer(original_question, answer_text, reality_text)
                    
                    if insight_title and insight_content:
                        # Save the new Insight
                        new_filename = f"{insight_title}.md"
                        new_filepath = os.path.join(INSIGHTS_DIR, new_filename)
                        
                        # Add SM-2 metadata
                        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                        final_markdown = f"""---
创建时间: {now}
分类: 个人洞见
标签: #个人洞见 #已内化
sm2_interval: 0
sm2_ease: 2.5
sm2_next_review: {datetime.date.today().strftime("%Y-%m-%d")}
---
# {insight_title}

{insight_content}
"""
                        with open(new_filepath, "w", encoding="utf-8") as f:
                            f.write(final_markdown)
                            
                        logger.info(f"✅ Promoted to Insight: {new_filename}")
                        
                        # Archive the original file
                        archive_path = os.path.join(ARCHIVES_DIR, filename)
                        shutil.move(filepath, archive_path)
                        processed_count += 1
                        
        except Exception as e:
            logger.error(f"Error processing open question {filename}: {e}")

    if processed_count > 0:
        logger.info(f"Processed {processed_count} answered questions into Insights.")


def generate_insight_from_answer(question: str, answer: str, reality: str) -> tuple[str, str]:
    """Uses Gemini 3.1 Pro to polish the user's raw thoughts into a formal Insight."""
    prompt = f"""你是一位顶尖的认知教练和文字精炼大师。用户刚刚回答了一个深度反思问题。
请将用户的原始回答进行“润色与提炼”，升华为一条具有极高价值的“个人原则”或“认知模型”。

要求：
1. **去粗取精**：提炼最核心的逻辑，语言要极其精炼、有力，像哲学金句或顶级商业原则。
2. **结构化**：输出一篇优雅的 Markdown 文章。
3. **输出格式（严格返回 JSON）**：
{{
    "title": "精炼的洞见标题，不要有任何标点或特殊字符",
    "content": "完整的 Markdown 格式正文内容"
}}

### 原始输入 ###
【原问题】：{question}
【用户的一句话回答】：{answer}
【用户的现实映射/补充逻辑】：{reality}

### 正文结构建议 ###
包含以下板块：
- **核心原则** (提炼出的核心一句话)
- **破局逻辑** (深度解释为什么这个原则有效)
- **行动箴言** (一句话的行动指引)
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "title": types.Schema(type=types.Type.STRING, description="精炼的洞见标题，不要有任何标点或特殊字符"),
                        "content": types.Schema(type=types.Type.STRING, description="完整的 Markdown 格式正文内容"),
                    },
                    required=["title", "content"]
                ),
                temperature=0.4
            )
        )
        
        # Robust JSON parsing
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()
            
        data = json.loads(raw_text)
        return data.get("title", ""), data.get("content", "")
    except Exception as e:
        logger.error(f"Failed to generate insight: {e}")
        return "", ""


def generate_weekly_cognitive_report():
    """
    Scans INSIGHTS_DIR for Insights created in the last 7 days.
    Generates a Weekly Rollup report.
    """
    logger.info("Generating Weekly Cognitive Report...")
    os.makedirs(WEEKLY_ROLLUP_DIR, exist_ok=True)
    
    if not os.path.isdir(INSIGHTS_DIR):
        return
        
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=7)
    recent_insights = []
    
    for filename in os.listdir(INSIGHTS_DIR):
        if not filename.endswith(".md"):
            continue
            
        filepath = os.path.join(INSIGHTS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Only include newly generated insights (they have #个人洞见)
            if "#个人洞见" in content:
                # Check modification time
                mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
                if mod_time >= cutoff_date:
                    recent_insights.append(content)
        except Exception as e:
            logger.warning(f"Error reading insight {filename}: {e}")
            
    if not recent_insights:
        logger.info("No new insights this week. Skipping report.")
        return
        
    # Generate the report
    insights_text = "\n\n---\n\n".join(recent_insights)
    prompt = f"""你是一位个人的首席认知官 (Chief Cognitive Officer)。
这是用户在本周内，通过深度反思和自我拷问，总结出的所有“个人洞见 (Insights)”。

请基于这些洞见，为用户写一份《本周个人认知迭代报告》。
这份报告应该像是一封专业、深刻、鼓舞人心的总结信，带领用户回顾他们这一周在“操作系统”层面发生的升级。

要求格式为 Markdown：
- 一个引人入胜的标题
- 整体认知进化脉络总结 (这周用户的思想重心在哪里？)
- 核心迭代点串联 (把不同卡片的洞见串联起来，找出暗线逻辑)
- CCO 寄语 (给下周的行动建议或警醒)

以下是本周的个人洞见：
{insights_text}
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.6
            )
        )
        
        now = datetime.datetime.now()
        report_filename = f"认知迭代周报_{now.strftime('%Y-%m-%d')}.md"
        report_path = os.path.join(WEEKLY_ROLLUP_DIR, report_filename)
        
        header = f"---\n创建时间: {now.strftime('%Y-%m-%d %H:%M')}\n标签: #每周复盘 #认知迭代\n---\n\n"
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(header + response.text)
            
        logger.info(f"✅ Generated Weekly Cognitive Report: {report_filename}")
        
    except Exception as e:
        logger.error(f"Failed to generate weekly report: {e}")
