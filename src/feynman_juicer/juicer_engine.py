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
        self.model = "gemini-3.7-flash"

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
                "【核心铁律与禁令】：\n"
                "1. 严禁生成大而化之的哲学鸡汤、空洞大口号或无用的概念说教！\n"
                "2. 落地实践必须强制转化为【IF-THEN 战备决策触发器】，每一个步骤必须在现实物理世界具备 0 阻力可执行性！\n\n"
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
                "  \"action_sop\": {\n"
                "    \"if_trigger\": \"明确客观的触发情境（身体/情绪信号、外部具体场景，绝不能是空泛口号，例如：'当坐在电脑前超过10分钟未开始并产生拖延念头时'）\",\n"
                "    \"then_checklist\": [\n"
                "      \"第1步：物理阻断/无脑微启动（<5秒极低摩擦动作，如站起来倒杯水、敲下一行TODO注释）\",\n"
                "      \"第2步：核心操作动作（具体执行步骤）\",\n"
                "      \"第3步：最小闭环交付（做完即停，绝不强求完美）\"\n"
                "    ],\n"
                "    \"else_fallback\": \"如果遇到巨大阻力或违规冲动时的熔断底线（如立刻合上电脑离开工位散步15分钟，严禁坐在工位假装工作）\"\n"
                "  }\n"
                "}\n\n"
                "要求：\n"
                "1. 绝不输出任何 JSON 之外的 Markdown 包装（不要 ```json），必须直接输出纯 JSON 字符串。\n"
                "2. 必须包含具体的时间戳，方便后续空降复习。\n"
                "3. action_sop 中的 then_checklist 必须极简，绝不要超过3步。"
            )
            
            import time
            response = None
            candidate_models = [self.model, "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
            models_to_try = list(dict.fromkeys(candidate_models))
            
            for curr_model in models_to_try:
                for attempt in range(3):
                    try:
                        logger.info(f"Generating content with model {curr_model} (attempt {attempt + 1})...")
                        response = self.client.models.generate_content(
                            model=curr_model,
                            contents=[uploaded_file, prompt],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json"
                            )
                        )
                        break
                    except Exception as e:
                        err_str = str(e)
                        if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"]):
                            delay = (attempt + 1) * 5
                            logger.warning(f"Gemini API limit/spike hit for {curr_model}. Retrying in {delay}s: {err_str}")
                            time.sleep(delay)
                        else:
                            logger.warning(f"Error calling {curr_model}: {e}, trying fallback...")
                            break
                if response:
                    break
                    
            if not response:
                raise RuntimeError("All candidate Gemini models failed during Feynman Juicer generation.")
            
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
        将提取出来的 JSON 渲染为 Obsidian 标准 If-Then 战备 Skill Card
        """
        import datetime
        tags_str = "\n  - ".join(data.get("tags", ["#未分类"]))
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        md = f"---\n"
        md += f"创建时间: {now_str}\n"
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
            
        md += f"## 🛠️ 落地与实践 (If-Then 战备触发器)\n"
        sop = data.get("action_sop")
        if isinstance(sop, dict):
            if_trigger = sop.get("if_trigger", "")
            then_steps = sop.get("then_checklist", [])
            else_fallback = sop.get("else_fallback", "")
            if if_trigger:
                md += f"- **🚨 IF（触发情境）**：{if_trigger}\n"
            if then_steps:
                md += f"- **🎯 THEN（极简执行清单）**：\n"
                for step in then_steps:
                    md += f"  - [ ] {step}\n"
            if else_fallback:
                md += f"- **🛑 ELSE（熔断底线）**：{else_fallback}\n\n"
        elif isinstance(sop, list):
            for step in sop:
                md += f"- [ ] {step}\n"
            md += "\n"
        elif isinstance(sop, str):
            md += f"{sop}\n\n"
            
        return md
