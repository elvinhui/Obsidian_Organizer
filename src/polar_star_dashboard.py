import os
import glob
import json
import logging
import datetime
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import frontmatter
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, POLAR_STAR_DIR, SKILL_COMPOUNDING_DIR

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

client = genai.Client(api_key=GEMINI_API_KEY)

# Ensure folders exist
os.makedirs(POLAR_STAR_DIR, exist_ok=True)
os.makedirs(SKILL_COMPOUNDING_DIR, exist_ok=True)

def create_mock_skill_logs_if_empty():
    """Generates mock logs if the Skill Compounding folder is empty, so the graph has data on day 1."""
    md_files = glob.glob(os.path.join(SKILL_COMPOUNDING_DIR, "*.md"))
    if md_files:
        return
        
    logger.info("Skill compounding directory is empty. Generating mock historical records for template and initial chart...")
    
    # 6 weeks of historical mock data leading up to today
    today = datetime.date.today()
    mock_data = [
        {"date": today - datetime.timedelta(weeks=5), "learning": 10.0, "lines": 500, "income": 0, "score": 70},
        {"date": today - datetime.timedelta(weeks=4), "learning": 12.5, "lines": 800, "income": 100, "score": 75},
        {"date": today - datetime.timedelta(weeks=3), "learning": 8.0, "lines": 400, "income": 0, "score": 68},
        {"date": today - datetime.timedelta(weeks=2), "learning": 15.0, "lines": 1200, "income": 400, "score": 82},
        {"date": today - datetime.timedelta(weeks=1), "learning": 18.0, "lines": 1500, "income": 800, "score": 88},
        {"date": today, "learning": 20.0, "lines": 2000, "income": 1200, "score": 92},
    ]
    
    for entry in mock_data:
        date_str = entry["date"].strftime("%Y-%m-%d")
        filepath = os.path.join(SKILL_COMPOUNDING_DIR, f"复利记录_{date_str}.md")
        content = f"""---
日期: {date_str}
学习时长: {entry['learning']}
代码行数: {entry['lines']}
技能收入: {entry['income']}
技能主观打分: {entry['score']}
---
# 📊 个人技能复利记录 - {date_str}

这是由 AI 引擎自动生成的模板记录。你可以修改上方的 YAML 数据来真实追踪你每周的成长情况。

- **学习时长**：本周花费在硬核技能学习上的时间（小时）
- **代码行数**：本周产出的量化代码行数（或者是其他产出计量）
- **技能收入**：通过技能资产本周变现所得 (元/美元)
- **技能主观打分**：你对自己本周执行力的主观打分 (1-100)
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
    logger.info("Mock records successfully generated.")

def get_financial_data(days=180) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetches Gold, US 10-Yr Yield, and S&P 500 from yfinance."""
    logger.info("Fetching macro market data from Yahoo Finance...")
    tickers = {
        "Gold": "GC=F",
        "US10Y": "^TNX",
        "SP500": "^GSPC"
    }
    
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)
    
    data_dict = {}
    for name, ticker in tickers.items():
        try:
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if not df.empty:
                # Yahoo finance returns multi-level column or plain Series based on query, let's normalize
                close_col = 'Close'
                if isinstance(df.columns, pd.MultiIndex):
                    # Handle multi-level columns by pulling the correct index
                    df.columns = df.columns.get_level_values(0)
                
                # Fetch closing price
                series = df[close_col]
                # Drop NaN
                series = series.dropna()
                data_dict[name] = series
        except Exception as e:
            logger.error(f"Failed to fetch ticker {ticker}: {e}")
            
    # Combine into single DataFrame
    macro_df = pd.DataFrame(data_dict)
    # Forward-fill missing values (for weekends/holidays)
    macro_df = macro_df.ffill().bfill()
    # Normalize to start from 100 for easy comparison
    macro_df_normalized = (macro_df / macro_df.iloc[0]) * 100
    
    return macro_df, macro_df_normalized

def get_skill_data() -> pd.DataFrame:
    """Parses local skill compounding markdown files."""
    logger.info("Parsing Obsidian skill compounding records...")
    records = []
    
    md_files = glob.glob(os.path.join(SKILL_COMPOUNDING_DIR, "*.md"))
    for filepath in md_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)
                
            # Read metadata with fallback support for Chinese/English keys
            date_val = post.metadata.get("日期") or post.metadata.get("date")
            if not date_val:
                continue
                
            if isinstance(date_val, datetime.date):
                date_parsed = date_val
            else:
                date_parsed = datetime.datetime.strptime(str(date_val).strip(), "%Y-%m-%d").date()
                
            learning = float(post.metadata.get("学习时长") or post.metadata.get("learning_hours") or 0)
            lines = float(post.metadata.get("代码行数") or post.metadata.get("coding_lines") or 0)
            income = float(post.metadata.get("技能收入") or post.metadata.get("monetization") or 0)
            score = float(post.metadata.get("技能主观打分") or post.metadata.get("skill_score") or 0)
            
            # Simple custom formula to calculate the composite compounding index
            # Code lines weighted down to not skew, income and learning hours weighted up
            compounding_index = (learning * 5.0) + (lines * 0.1) + (income * 0.5) + (score * 0.2)
            
            records.append({
                "Date": pd.to_datetime(date_parsed),
                "LearningHours": learning,
                "CodingLines": lines,
                "Income": income,
                "SubjectiveScore": score,
                "CompoundingIndex": compounding_index
            })
        except Exception as e:
            logger.error(f"Error parsing skill log {os.path.basename(filepath)}: {e}")
            
    if not records:
        return pd.DataFrame()
        
    df = pd.DataFrame(records)
    df = df.sort_values(by="Date").reset_index(drop=True)
    return df

def generate_dashboard():
    """Main execution orchestrator."""
    create_mock_skill_logs_if_empty()
    
    # 1. Fetch Market Data
    try:
        macro_raw, macro_norm = get_financial_data(days=180)
    except Exception as e:
        logger.error(f"Failed to process macro financial data: {e}")
        return
        
    # 2. Parse User Data
    skill_df = get_skill_data()
    if skill_df.empty:
        logger.error("No skill compounding records found even after mock generation.")
        return
        
    # 3. Align dates and Plot
    logger.info("Generating North Star dashboard chart...")
    fig, ax1 = plt.subplots(figsize=(10, 5))
    
    # Support Chinese characters in matplotlib (fallback list for safety)
    for font in ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']:
        plt.rcParams['font.sans-serif'] = [font]
        try:
            # Test plot text to see if it throws error
            fig.canvas.draw()
            break
        except Exception:
            continue
            
    plt.rcParams['axes.unicode_minus'] = False
    
    # Plot Macro Indicators
    ax1.plot(macro_norm.index, macro_norm['Gold'], label='黄金价格 (标化)', color='#DAA520', alpha=0.8, linewidth=2)
    ax1.plot(macro_norm.index, macro_norm['US10Y'], label='10年美债收益率 (标化)', color='#4682B4', alpha=0.6, linewidth=1.5)
    ax1.plot(macro_norm.index, macro_norm['SP500'], label='标普500指数 (标化)', color='#2E8B57', alpha=0.6, linewidth=1.5)
    
    ax1.set_xlabel('时间', fontsize=12)
    ax1.set_ylabel('宏观走势 (以180天前为基准100)', fontsize=12)
    ax1.tick_params(axis='y')
    ax1.grid(True, linestyle='--', alpha=0.3)
    
    # Create twin axis for personal skill metrics
    ax2 = ax1.twinx()
    ax2.plot(skill_df['Date'], skill_df['CompoundingIndex'], label='个人技能复利指数', color='#FF4500', marker='o', linewidth=2.5)
    ax2.set_ylabel('个人复利指数 (复合积分)', color='#FF4500', fontsize=12)
    ax2.tick_params(axis='y', labelcolor='#FF4500')
    
    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.title('🧭 北极星：宏观防守与个体成长复利态势图', fontsize=14, fontweight='bold', pad=15)
    plt.tight_layout()
    
    chart_path = os.path.join(POLAR_STAR_DIR, "北极星姿态图.png")
    plt.savefig(chart_path, dpi=150)
    plt.close()
    logger.info(f"Chart saved to {chart_path}")
    
    # 4. Generate Strategic Audit using Gemini
    logger.info("Generating strategic audit with Gemini...")
    latest_gold = macro_raw['Gold'].iloc[-1].item() if not macro_raw['Gold'].empty else 0
    latest_us10y = macro_raw['US10Y'].iloc[-1].item() if not macro_raw['US10Y'].empty else 0
    latest_sp = macro_raw['SP500'].iloc[-1].item() if not macro_raw['SP500'].empty else 0
    
    latest_skill = skill_df.iloc[-1]
    
    prompt = f"""
    You are a legendary macro-economic strategist and CBT personal coach (combining Ray Dalio's principles and Charlie Munger's wisdom).
    Analyze this combined data of the external macro environment and the user's micro-level skill assets.
    
    【宏观市场最新数据】
    - 黄金价格: ${latest_gold:.2f}/盎司 (避险情绪指标)
    - 10年期美债收益率: {latest_us10y:.2f}% (全球资产定价之锚)
    - 标普500指数: {latest_sp:.2f} (大盘风险偏好)
    
    【个人技能复利最新数据 (本周)】
    - 学习投入时长: {latest_skill['LearningHours']:.1f} 小时
    - 代码产出量: {latest_skill['CodingLines']:.0f} 行
    - 变现收入: {latest_skill['Income']:.2f} 元
    - 主观精力/执行力评分: {latest_skill['SubjectiveScore']:.0f}/100
    - 复合复利指数: {latest_skill['CompoundingIndex']:.2f}
    
    任务：
    请写一段犀利、透彻、具有防御与对冲战略智慧的审计评估（中文，控制在 150-250 字）。
    1. 评估当前的宏观风险（美债收益率与黄金变动暗示的风险）。
    2. 对照个人本周的技能复利数据，给出我们是在“战术勤奋”还是在构建真正的“能力护城河”。
    3. 给出一个“肉身对冲”的下周行动建议。
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt
        )
        audit_text = response.text
    except Exception as e:
        logger.error(f"Failed to generate Gemini audit: {e}")
        audit_text = "⚠️ 战略审计暂时生成失败，请检查 Gemini API 额度与网络连接。"
        
    # 5. Write Markdown Dashboard File
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    md_content = f"""---
创建时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
标签: #北极星看板 #数据可视化 #复利审计
---
# 🧭 北极星：宏观防守与个体复利监控看板 ({today_str})

> 本看板由 `polar_star_dashboard.py` 自动生成。它通过比对外部的全球宏观资产（黄金、美债收益率）与你内部的技能复利曲线，帮助你实时校准精力分配，构建防守型个人增长壁垒。

## 📈 态势可视化

![北极星姿态图](北极星姿态图.png)

---

## 👨‍💼 宏观防守与个体成长战略审计
{audit_text}

---

## 📊 本周关键指标快照

| 指标维度 | 最新值 | 战略定位与防御意义 |
| :--- | :--- | :--- |
| **🥇 避险黄金** | ${latest_gold:.2f}/盎司 | 衡量全球系统性危机与法币信用危机的核心锚点。 |
| **💵 美债收益率** | {latest_us10y:.2f}% | 全球无风险资产收益率。它越高，流动性越紧张，个体越应当降杠杆。 |
| **🎯 复合复利指数** | {latest_skill['CompoundingIndex']:.2f} | 你的个人核心壁垒分值。这是唯一不受宏观泡沫影响的“确定性资产”。 |
| **💰 变现数据** | {latest_skill['Income']:.2f} 元 | 技能变现成果。将“技能”资产转化为“现金”的直接效率体现。 |

---
*“在泡沫中防御，在复利中跃迁。做时间的朋友，构建无法被通胀剥夺的个人能力护城河。”*
"""

    filepath = os.path.join(POLAR_STAR_DIR, "北极星监控看板.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    logger.info(f"✅ North Star Dashboard generated successfully: {filepath}")

if __name__ == "__main__":
    generate_dashboard()
