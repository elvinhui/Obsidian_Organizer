import os
import json
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class JuicerEngine:
    def __init__(self, api_key=None):
        if not api_key:
            from dotenv import load_dotenv
            load_dotenv()
            # fallback to lightsail_bot
            if not os.getenv("GEMINI_API_KEY"):
                load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lightsail_bot", ".env"))
            api_key = os.getenv("GEMINI_API_KEY")
            
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
            
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-1.5-flash"

    def juice_audio(self, audio_path: str) -> dict:
        """
        上传音频并使用 Gemini 进行高密度降维榨汁，返回结构化 JSON
        """
        logger.info(f"Uploading audio to Gemini: {audio_path}")
        uploaded_file = None
        try:
            # Upload the file
            uploaded_file = self.client.files.upload(file=audio_path)
            logger.info(f"Audio uploaded successfully. File URI: {uploaded_file.uri}")
            
            prompt = (
                "你是一个极其硬核的“多模态降维榨汁机 (Feynman-Juicer)”。\n"
                "你的任务是听取提供的音频文件，并将其中的碎片化信息、废话、情绪、营销话术统统剥离，进行高密度提炼，输出为结构化的 JSON 格式。\n\n"
                "必须包含以下字段：\n"
                "{\n"
                "  \"title\": \"从视频中提取的精炼核心主题，不超过15个字\",\n"
                "  \"tags\": [\"#认知提升\", \"#具体领域\"],\n"
                "  \"core_concepts\": [\n"
                "    {\n"
                "      \"timestamp\": \"原视频对应的时间戳，例如 [01:23]\",\n"
                "      \"concept\": \"核心痛点或认知模型名称\",\n"
                "      \"explanation\": \"费曼式大白话解释，一针见血，必须使用大白话翻译\"\n"
                "    }\n"
                "  ],\n"
                "  \"action_sop\": [\n"
                "    \"第一步：...\",\n"
                "    \"第二步：...\"\n"
                "  ]\n"
                "}\n\n"
                "要求：\n"
                "1. 绝不输出任何 JSON 之外的 Markdown 包装（不要 ```json），必须直接输出纯 JSON 字符串。\n"
                "2. 必须包含具体的时间戳，方便后续空降复习。"
            )
            
            logger.info("Generating content...")
            response = self.client.models.generate_content(
                model=self.model,
                contents=[uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            # 尝试解析 JSON
            text = response.text.strip()
            # 容错：如果模型还是加了 markdown
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
                
            return json.loads(text)
            
        except Exception as e:
            logger.error(f"Failed to juice audio: {e}")
            raise
        finally:
            if uploaded_file:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                    logger.info("Cleaned up uploaded file from Gemini.")
                except Exception as e:
                    logger.warning(f"Failed to delete file from Gemini: {e}")

    def render_obsidian_card(self, data: dict, original_url: str) -> str:
        """
        将提取出来的 JSON 渲染为 Obsidian 标准 Skill Card
        """
        tags_str = "\n  - ".join(data.get("tags", ["#未分类"]))
        
        md = f"---\n"
        md += f"tags:\n  - {tags_str}\n"
        md += f"sm2_ease: 2.5\n"
        md += f"sm2_interval: 1\n"
        md += f"source: {original_url}\n"
        md += f"---\n\n"
        md += f"# {data.get('title', 'Untitled Idea')}\n\n"
        
        md += f"## 💡 核心概念\n"
        for concept in data.get("core_concepts", []):
            timestamp = concept.get('timestamp', '[00:00]')
            name = concept.get('concept', '未命名模型')
            explanation = concept.get('explanation', '')
            md += f"**{timestamp} {name}**\n{explanation}\n\n"
            
        md += f"## 🛠️ 落地与实践 (Action & SOP)\n"
        for step in data.get("action_sop", []):
            md += f"- [ ] {step}\n"
            
        return md
