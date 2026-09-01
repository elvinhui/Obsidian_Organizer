import sys
import os

# Add src to path if running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.semantic_router.matcher import find_best_prompt
from src.semantic_router.engine import render_prompt, execute_prompt

def process_text(text):
    print("🧠 Semantic-Router 启动...")
    best_file, score = find_best_prompt(text)
    
    if not best_file:
        print("❌ 未找到匹配的提示词模板。请确保已运行 python -m src.semantic_router.cache 更新缓存。")
        return None
        
    print(f"✅ 匹配到最佳模板: {os.path.basename(best_file)} (置信度: {score:.4f})")
    
    print("⚙️ 正在生成 Prompt...")
    final_prompt = render_prompt(best_file, text)
    
    print("🚀 正在请求 Gemini 2.5 Flash 进行生成...")
    result = execute_prompt(final_prompt)
    
    print("\n" + "="*40 + " 生成结果 " + "="*40 + "\n")
    print(result)
    print("\n" + "="*90)
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m src.semantic_router.cli \"你要处理的文本\"")
        sys.exit(1)
        
    user_text = sys.argv[1]
    process_text(user_text)
