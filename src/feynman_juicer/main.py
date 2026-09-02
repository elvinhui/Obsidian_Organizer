import os
import logging
from .inbox_parser import InboxParser
from .media_extractor import MediaExtractor
from .juicer_engine import JuicerEngine

logger = logging.getLogger(__name__)

def run_feynman_juicer(inbox_file_path: str, output_dir: str):
    """
    执行完整的多模态榨汁流水线
    """
    logger.info(f"Starting Feynman Juicer on {inbox_file_path}")
    
    parser = InboxParser(inbox_file_path)
    urls = parser.get_pending_urls()
    
    if not urls:
        logger.info("No pending URLs found. Everything is juiced!")
        return
        
    logger.info(f"Found {len(urls)} pending URLs.")
    
    extractor = MediaExtractor()
    engine = JuicerEngine()
    
    os.makedirs(output_dir, exist_ok=True)
    
    for item in urls:
        url = item['url']
        line_idx = item['line_idx']
        
        try:
            # 1. 物理提取层
            audio_path = extractor.download_audio(url)
            
            # 2. 多模态榨汁层
            data = engine.juice_audio(audio_path)
            
            # 3. 渲染与保存
            md_content = engine.render_obsidian_card(data, url)
            
            # 使用 title 作为文件名，清洗非法字符
            safe_title = "".join(c for c in data.get('title', 'Untitled') if c.isalnum() or c in (' ', '-', '_')).strip()
            out_file = os.path.join(output_dir, f"{safe_title}.md")
            
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(md_content)
                
            logger.info(f"Successfully generated Skill Card: {out_file}")
            
            # 4. 回写状态标记为 #已处理
            parser.mark_status(line_idx, "#已处理")
            
            # 清理物理层的音频文件 (减少磁盘占用)
            if os.path.exists(audio_path):
                os.remove(audio_path)
                
        except Exception as e:
            logger.error(f"Failed to process URL {url}: {e}")
            # 回写失败状态
            parser.mark_status(line_idx, "#Failed")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # 可以通过命令行或者配置传入
    # run_feynman_juicer("C:/Users/.../Inbox.md", "C:/Users/.../JuicedCards")
