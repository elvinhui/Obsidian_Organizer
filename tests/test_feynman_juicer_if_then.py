import os
import pytest
from src.feynman_juicer.juicer_engine import JuicerEngine
from src.template_engine import render_and_save

def test_render_obsidian_card_with_if_then_dict():
    # Pass dummy api_key to avoid needing real key for offline test
    engine = JuicerEngine(api_key="fake-api-key-for-unit-test")
    
    data = {
        "title": "反拖延物理熔断",
        "tags": ["#认知提升", "#行动力"],
        "core_concepts": [
            {
                "timestamp": "[01:30]",
                "concept": "状态依赖陷阱",
                "explanation": "不要等待有心情再开始，用物理动作直接启动神经回路。"
            }
        ],
        "action_sop": {
            "if_trigger": "当坐在工位超过10分钟未开始并产生拖延念头时",
            "then_checklist": [
                "离开椅子去倒一杯水（打破身体静止惯性）",
                "回到电脑前敲下一行 TODO 注释",
                "允许自己做满 3 分钟即可放弃"
            ],
            "else_fallback": "若依然极度抗拒，立刻合上电脑离开工位散步15分钟，严禁假装工作。"
        }
    }
    
    card_md = engine.render_obsidian_card(data, "https://v.douyin.com/mock_video")
    
    assert "# 反拖延物理熔断" in card_md
    assert "## 🛠️ 落地与实践 (If-Then 战备触发器)" in card_md
    assert "- **🚨 IF（触发情境）**：当坐在工位超过10分钟未开始并产生拖延念头时" in card_md
    assert "- **🎯 THEN（极简执行清单）**：" in card_md
    assert "- [ ] 离开椅子去倒一杯水（打破身体静止惯性）" in card_md
    assert "- [ ] 回到电脑前敲下一行 TODO 注释" in card_md
    assert "- [ ] 允许自己做满 3 分钟即可放弃" in card_md
    assert "- **🛑 ELSE（熔断底线）**：若依然极度抗拒，立刻合上电脑离开工位散步15分钟，严禁假装工作。" in card_md

def test_render_obsidian_card_backward_compatibility():
    engine = JuicerEngine(api_key="fake-api-key-for-unit-test")
    
    # 1. Legacy list format
    data_list = {
        "title": "旧版列表测试",
        "tags": ["#测试"],
        "core_concepts": [],
        "action_sop": ["步骤一", "步骤二"]
    }
    card_md_list = engine.render_obsidian_card(data_list, "https://mock.com")
    assert "- [ ] 步骤一" in card_md_list
    assert "- [ ] 步骤二" in card_md_list
    
    # 2. String format
    data_str = {
        "title": "旧版字符串测试",
        "tags": ["#测试"],
        "core_concepts": [],
        "action_sop": "- 🚨 IF: 测试情境\n- 🎯 THEN: 测试动作"
    }
    card_md_str = engine.render_obsidian_card(data_str, "https://mock.com")
    assert "测试情境" in card_md_str

def test_template_engine_core_knowledge_if_then(tmp_path, monkeypatch):
    import src.template_engine
    monkeypatch.setattr(src.template_engine, "SKILLS_DIR", str(tmp_path))
    
    mock_sop = (
        "- **🚨 IF（触发情境）**：当准备做实盘交易下单前\n"
        "- **🎯 THEN（极简执行清单）**：\n"
        "  - [ ] 1. 关闭交易软件倒计时锁定 30 分钟\n"
        "  - [ ] 2. 检查单笔最大亏损是否小于总资产 2%\n"
        "- **🛑 ELSE（熔断底线）**：只要有任何一条不满足，立刻强行关闭下单窗口。"
    )
    
    data = {
        "category": "认知提升",
        "title": "交易冷静期触发器",
        "tags": ["#投资", "#风控"],
        "core_concepts": "避免FOMO冲动交易。",
        "action_sop": mock_sop,
        "connections": "- 涉及损失厌恶与双系统决策。"
    }
    
    saved_path = render_and_save(data)
    assert os.path.exists(saved_path)
    
    with open(saved_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "## 🛠️ 落地与实践 (If-Then 战备触发器)" in content
    assert "🚨 IF（触发情境）" in content
    assert "🎯 THEN（极简执行清单）" in content
    assert "🛑 ELSE（熔断底线）" in content
