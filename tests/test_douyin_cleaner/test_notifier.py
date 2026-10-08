import pytest
from src.douyin_cleaner.notifier import (
    build_audit_report,
    build_cleanup_report,
    format_user_summary,
)

def test_build_audit_report():
    stats = {
        "total": 120,
        "audited": 100,
        "canceled": 12,
        "inactive_180": 25,
        "inactive_360": 10,
        "pending": 20
    }
    report = build_audit_report(stats)
    assert "抖音关注列表审计完成" in report
    assert "总关注数: 120" in report
    assert "已注销账号: 12" in report
    assert "超过半年未更新: 25" in report

def test_build_cleanup_report():
    summary = {
        "total_targets": 15,
        "success_count": 14,
        "error_count": 1,
        "canceled_count": 5,
        "inactive_count": 10
    }
    report = build_cleanup_report(summary)
    assert "抖音关注列表清理战报" in report
    assert "成功取关: 14" in report
    assert "失败/跳过: 1" in report

def test_format_user_summary():
    users = [
        {"nickname": "注销小号", "is_canceled": 1, "days_inactive": 999},
        {"nickname": "断更博主", "is_canceled": 0, "days_inactive": 210}
    ]
    formatted = format_user_summary(users)
    assert "注销小号" in formatted
    assert "断更博主" in formatted
