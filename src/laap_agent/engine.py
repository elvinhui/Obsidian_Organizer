import os
from datetime import datetime
import json
from google import genai
from pydantic import BaseModel

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import GEMINI_API_KEY, INBOX_DIR, INSIGHTS_DIR, LAAP_FEEDBACK_DIR, LAAP_IDENTITY_FILE
from .models import AgentContext, PSI5State, SimulationResult, MemoryEntry
from .db import get_latest_psi5, save_memory, init_db

# Initialize GenAI client
client = genai.Client(api_key=GEMINI_API_KEY)

def perceive_environment() -> AgentContext:
    """Reads Inbox tasks, recent insights, and identity kernel to form context."""
    pending_tasks = []
    if os.path.exists(INBOX_DIR):
        for f in os.listdir(INBOX_DIR):
            if f.endswith('.md'):
                pending_tasks.append(f)
                
    recent_insights = []
    if os.path.exists(INSIGHTS_DIR):
        files = [f for f in os.listdir(INSIGHTS_DIR) if f.endswith('.md')]
        # get 3 most recent insights
        files.sort(key=lambda x: os.path.getmtime(os.path.join(INSIGHTS_DIR, x)), reverse=True)
        recent_insights = files[:3]
        
    identity_kernel = ""
    if os.path.exists(LAAP_IDENTITY_FILE):
        with open(LAAP_IDENTITY_FILE, 'r', encoding='utf-8') as f:
            identity_kernel = f.read()
            
    return AgentContext(
        pending_tasks=pending_tasks,
        recent_insights=recent_insights,
        identity_kernel=identity_kernel
    )

def calculate_psi5_before(context: AgentContext) -> PSI5State:
    """Calculate pre-simulation PSI5 state based on recent history and environment."""
    current_state = get_latest_psi5()
    
    # Simple heuristics: 
    # High pending tasks -> low certainty, low energy
    if len(context.pending_tasks) > 5:
        current_state.certainty = max(0, current_state.certainty - 10)
        current_state.energy = max(0, current_state.energy - 10)
        
    # Having new insights -> high competence
    if len(context.recent_insights) > 0:
        current_state.competence = min(100, current_state.competence + 5)
        
    return current_state

def run_forward_simulation(context: AgentContext, psi5_before: PSI5State) -> SimulationResult:
    """Uses Gemini 3.1 Pro to simulate consequences and adjust PSI5 state."""
    
    prompt = f"""
    你是一个运行在 LAAP 架构下的“个人数字生命体 (Digital Twin)”。
    你需要根据我的身份设定、我当前的心理状态 (PSI5) 以及环境中的信息，进行“反事实推演”。
    
    【身份基座】
    {context.identity_kernel}
    
    【当前状态】
    Inbox 待办任务: {', '.join(context.pending_tasks) if context.pending_tasks else '无'}
    最近新洞见: {', '.join(context.recent_insights) if context.recent_insights else '无'}
    推演前心理状态 (0-100): 
    能量(Energy)={psi5_before.energy}, 确定感(Certainty)={psi5_before.certainty}, 胜任感(Competence)={psi5_before.competence}
    
    【任务】
    1. 模拟推演：如果今天我只处理这些待办，或者陷入当前的节奏，会对我的“长期身份目标”产生什么 2 阶和 3 阶后果？
    2. 计算推演后的 PSI5 状态，给出数值。
    3. 给出给“肉身自我”的具体行动建议。
    """
    
    # Call Gemini with structured output
    response = client.models.generate_content(
        model='gemini-3.5-flash',
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SimulationResult,
        ),
    )
    
    result_dict = json.loads(response.text)
    
    # Overwrite date
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result_dict["date"] = now_str
    
    return SimulationResult(**result_dict)

def save_feedback_card(sim_result: SimulationResult):
    """Save the feedback into Obsidian."""
    os.makedirs(LAAP_FEEDBACK_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"🧬 分身推演报告_{date_str}.md"
    filepath = os.path.join(LAAP_FEEDBACK_DIR, filename)
    
    content = f"""---
创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
标签: #LAAP #推演报告
状态: 已生成
---
# 🧬 数字生命体推演报告 ({date_str})

## 📊 PSI5 状态变迁
- **能量 (Energy)**: {sim_result.psi5_after.energy:.1f}
- **确定感 (Certainty)**: {sim_result.psi5_after.certainty:.1f}
- **胜任感 (Competence)**: {sim_result.psi5_after.competence:.1f}
- **自主选择权 (Autonomy)**: {sim_result.psi5_after.autonomy:.1f}
- **归属感 (Affiliation)**: {sim_result.psi5_after.affiliation:.1f}

## 🧠 反事实推演分析
{sim_result.analysis}

## ⚡ 破局行动建议
{sim_result.action_advice}

> *来自数字分身的寄语：时刻对齐长期身份目标，做时间的朋友。*
"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def run_daily_simulation():
    """Main pipeline for the agent."""
    init_db()
    context = perceive_environment()
    psi5_before = calculate_psi5_before(context)
    sim_result = run_forward_simulation(context, psi5_before)
    
    entry = MemoryEntry(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        context=context,
        psi5_state_before=psi5_before,
        simulation_result=sim_result
    )
    
    save_memory(entry)
    save_feedback_card(sim_result)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"LAAP Simulation completed. Feedback saved to {LAAP_FEEDBACK_DIR}")

if __name__ == "__main__":
    run_daily_simulation()
