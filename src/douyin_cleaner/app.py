import streamlit as st
import asyncio
import os
import pandas as pd
from typing import List, Dict, Any

from src.douyin_cleaner.db import (
    init_db,
    get_followings,
    get_audit_stats,
    update_following_status,
    DEFAULT_DB_PATH
)
from src.douyin_cleaner.scraper import scrape_following_list, find_auth_file
from src.douyin_cleaner.auditor import audit_followings_batch
from src.douyin_cleaner.cleaner import execute_clean_targets
from src.douyin_cleaner.notifier import (
    load_telegram_config,
    build_audit_report,
    send_telegram_notification
)

# Page configuration
st.set_page_config(
    page_title="抖音关注列表清理助手",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Ensure database initialized
init_db(DEFAULT_DB_PATH)

# Header
st.title("🧹 抖音关注列表清理助手 (Douyin Cleaner)")
st.caption("基于本地静默无头浏览器的关注列表低频审计、批量过滤与安全取关工具。绝不弹出浏览器窗口，战报直达 Telegram。")

# Check credentials
auth_path = find_auth_file()
tg_token, tg_chat_id = load_telegram_config()

with st.sidebar:
    st.header("⚙️ 系统状态与配置")
    if auth_path:
        st.success(f"✅ 抖音凭据有效:\n`{os.path.basename(auth_path)}`")
    else:
        st.error("❌ 未找到 douyin_auth.json，请先登录导出凭据。")
        
    if tg_token and tg_chat_id:
        st.success(f"✅ Telegram 通知已就绪\nChat ID: `{tg_chat_id}`")
    else:
        st.warning("⚠️ Telegram 未完全配置，可在 .env 中配置 TELEGRAM_CHAT_ID。")

    st.markdown("---")
    st.subheader("🛠️ 大规模抓取与审计参数")
    
    preset = st.selectbox(
        "快速预设模式",
        ["自定义参数", "⚡ 体验测试 (50次 / 约1,000人)", "🚀 中度嗅探 (250次 / 约5,000人)", "🏆 万人全量嗅探 (600次 / 约12,000人)"],
        index=0
    )
    
    default_scroll = 300
    if "50次" in preset:
        default_scroll = 50
    elif "250次" in preset:
        default_scroll = 250
    elif "600次" in preset:
        default_scroll = 600

    scroll_limit = st.slider(
        "嗅探滚动次数上限",
        min_value=20,
        max_value=1200,
        value=default_scroll,
        step=20,
        help="每次滚动捕获约 20 人。600 次约 12,000 人。系统实时自动入库，即使中途终止也不丢失已抓取数据。"
    )
    
    audit_batch_size = st.slider(
        "每批次审计数量",
        min_value=20,
        max_value=1000,
        value=100,
        step=20,
        help="建议每次 100~300 人，多批次分步审计以维持最佳抗风控状态。"
    )
    
    st.markdown("---")
    if st.button("🔔 测试 Telegram 消息推送", use_container_width=True):
        res = send_telegram_notification("🤖 **抖音清理助手测试**：Telegram 联动通路测试正常！")
        if res:
            st.toast("✅ 测试消息已发送至您的 Telegram！", icon="📨")
        else:
            st.error("发送失败，请检查 Bot Token 与 Chat ID。")

# Top metrics
stats = get_audit_stats(DEFAULT_DB_PATH)
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("总关注人数", stats["total"])
m2.metric("已完成审计", stats["audited"])
m3.metric("待审计", stats["pending"])
m4.metric("🪦 已注销账号", stats["canceled"])
m5.metric("💤 断更半年以上", stats["inactive_180"])
m6.metric("✅ 已取关数量", stats["deleted"])

st.markdown("---")

# Action Bar: Scrape & Audit
col_act1, col_act2, col_act3 = st.columns(3)

with col_act1:
    st.markdown("#### 步骤 1: 嗅探关注列表")
    if st.button("🌐 开始静默抓取关注列表", use_container_width=True):
        if not auth_path:
            st.error("缺少凭证文件，无法启动抓取。")
        else:
            progress_placeholder = st.empty()
            with st.spinner("正在后台无头模式抓取关注列表，请稍候..."):
                def update_progress(msg, count):
                    progress_placeholder.info(f"⏳ {msg}")
                try:
                    total_scraped, new_saved = asyncio.run(
                        scrape_following_list(
                            db_path=DEFAULT_DB_PATH,
                            auth_file=auth_path,
                            max_scrolls=scroll_limit,
                            headless=True,
                            progress_callback=update_progress
                        )
                    )
                    progress_placeholder.empty()
                    st.success(f"🎉 抓取完成！共嗅探到 {total_scraped} 人，新入库/更新 {new_saved} 人。")
                    st.rerun()
                except Exception as e:
                    st.error(f"抓取失败: {e}")

with col_act2:
    st.markdown("#### 步骤 2: 静默低频审计")
    if st.button(f"🔍 审计待分析账号 (前 {audit_batch_size} 人)", use_container_width=True):
        if not auth_path:
            st.error("缺少凭证文件，无法启动审计。")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            with st.spinner("正在后台低频探测账号活跃度，规避风控中..."):
                def update_audit(msg, cur, tot):
                    status_text.text(msg)
                    progress_bar.progress(cur / tot)
                try:
                    audited_count = asyncio.run(
                        audit_followings_batch(
                            db_path=DEFAULT_DB_PATH,
                            auth_file=auth_path,
                            limit=audit_batch_size,
                            headless=True,
                            progress_callback=update_audit
                        )
                    )
                    status_text.empty()
                    progress_bar.empty()
                    st.success(f"✅ 本批次审计完成！共处理 {audited_count} 人。")
                    
                    # Optionally push audit summary to Telegram
                    new_stats = get_audit_stats(DEFAULT_DB_PATH)
                    send_telegram_notification(build_audit_report(new_stats))
                    st.rerun()
                except Exception as e:
                    st.error(f"审计失败: {e}")

with col_act3:
    st.markdown("#### 步骤 3: 一键推算建议")
    st.info("💡 建议：\n1. 优先清理已注销账号（头像为默认沙子）；\n2. 勾选清理断更 180 天以上的营销/停更账号。")

st.markdown("---")

# Main content: Interactive Table
st.subheader("📋 待清理关注账号确认面板")

# Filter controls
fc1, fc2, fc3, fc4, fc5 = st.columns(5)
with fc1:
    filter_only_candidates = st.checkbox("仅看建议清理目标 (🪦注销/💤断更)", value=True)
with fc2:
    filter_canceled = st.checkbox("仅看已注销账号 (🪦)", value=False)
with fc3:
    filter_inactive_180 = st.checkbox("断更 > 180 天 (💤)", value=False)
with fc4:
    filter_inactive_360 = st.checkbox("断更 > 360 天 (🧊)", value=False)
with fc5:
    display_limit_choice = st.selectbox("每页展示条数", [100, 250, 500, 1000, "全部"], index=1)

# Query data
min_days = None
if filter_inactive_360:
    min_days = 360
elif filter_inactive_180:
    min_days = 180

raw_users = get_followings(
    db_path=DEFAULT_DB_PATH,
    is_canceled=True if filter_canceled else None,
    min_inactive_days=min_days
)

# Filter out deleted
raw_users = [u for u in raw_users if u.get("audit_status") != "deleted"]

if filter_only_candidates:
    raw_users = [u for u in raw_users if u.get("is_canceled") or (u.get("days_inactive", 0) >= 180)]

limit_num = len(raw_users)
if isinstance(display_limit_choice, int):
    limit_num = display_limit_choice

display_users = raw_users[:limit_num]

st.caption(f"📊 满足筛选条件的账号总数: **{len(raw_users)}** 人，下方表格载入前 **{len(display_users)}** 人（防卡顿优化）。")

if not display_users:
    st.info("当前筛选条件下没有待处理的账号。可取消上方过滤器查看全部，或点击步骤 1 / 步骤 2 补充抓取与审计。")
else:
    # Build dataframe for data_editor
    table_rows = []
    for u in display_users:
        sec_uid = u["sec_uid"]
        is_canceled = bool(u.get("is_canceled", 0))
        days = u.get("days_inactive", 0)
        # Default recommend clean if canceled or inactive >= 180 days
        recommended = is_canceled or (days >= 180)
        
        status_label = "待审计"
        if u.get("audit_status") == "deleted":
            status_label = "✅ 已取关"
        elif is_canceled:
            status_label = "🪦 已注销"
        elif days >= 360:
            status_label = "🧊 断更 > 1年"
        elif days >= 180:
            status_label = "💤 断更 > 半年"
        elif u.get("audit_status") == "audited":
            status_label = "🟢 正常活跃"

        table_rows.append({
            "待清理": recommended,
            "昵称": u.get("nickname", "未知"),
            "状态": status_label,
            "断更天数": days,
            "最新作品时间": u.get("last_publish_time") or "未知",
            "备注": u.get("audit_note") or "",
            "sec_uid": sec_uid
        })

    df = pd.DataFrame(table_rows)

    edited_df = st.data_editor(
        df,
        column_config={
            "待清理": st.column_config.CheckboxColumn("清理勾选", default=False),
            "sec_uid": None, # Hide internal ID
            "昵称": st.column_config.TextColumn("账号昵称", width="medium"),
            "状态": st.column_config.TextColumn("审计判定", width="small"),
            "断更天数": st.column_config.NumberColumn("断更天数", format="%d 天"),
            "最新作品时间": st.column_config.TextColumn("最新作品"),
            "备注": st.column_config.TextColumn("详情备注", width="large")
        },
        disabled=["昵称", "状态", "断更天数", "最新作品时间", "备注"],
        hide_index=True,
        use_container_width=True
    )

    selected_rows = edited_df[edited_df["待清理"] == True]
    selected_sec_uids = selected_rows["sec_uid"].tolist()
    
    st.markdown("---")
    st.markdown(f"#### 🎯 已确认选中 **{len(selected_sec_uids)}** 个账号准备清理")

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        if st.button(f"🚀 确认静默取关选中的 {len(selected_sec_uids)} 人并推送战报", type="primary", use_container_width=True):
            if not selected_sec_uids:
                st.warning("您尚未勾选任何待清理的账号！")
            elif not auth_path:
                st.error("缺少凭证文件，无法执行取关。")
            else:
                clean_status = st.empty()
                clean_progress = st.progress(0)
                with st.spinner("正在后台静默执行安全取关（间隔休眠 3~5 秒以抗风控）..."):
                    def update_clean(msg, cur, tot):
                        clean_status.text(msg)
                        clean_progress.progress(cur / tot)

                    try:
                        summary = asyncio.run(
                            execute_clean_targets(
                                db_path=DEFAULT_DB_PATH,
                                target_sec_uids=selected_sec_uids,
                                auth_file=auth_path,
                                headless=True,
                                notify_telegram=True,
                                progress_callback=update_clean
                            )
                        )
                        clean_status.empty()
                        clean_progress.empty()
                        st.success(
                            f"🎉 取关清理完成！成功: {summary['success_count']} 人，失败/跳过: {summary['error_count']} 人。\n"
                            "战报已成功推送到您的 Telegram！"
                        )
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"清理执行过程中出错: {e}")

    with col_info:
        st.caption("🛡️ **风控保护声明**：批量取关会在后台模拟真实操作，账号间自动设置随机冷冻时间。若遭遇抖音弹窗验证码，系统会安全熔断终止并向 Telegram 发送报警截图，确保账号安全。")
