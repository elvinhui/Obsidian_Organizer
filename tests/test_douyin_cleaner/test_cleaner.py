import pytest
from src.douyin_cleaner.cleaner import aggregate_cleanup_summary

def test_aggregate_cleanup_summary():
    results = [
        {"sec_uid": "U1", "status": "deleted", "is_canceled": 1, "days_inactive": 999},
        {"sec_uid": "U2", "status": "deleted", "is_canceled": 0, "days_inactive": 200},
        {"sec_uid": "U3", "status": "error", "is_canceled": 0, "days_inactive": 190},
    ]
    summary = aggregate_cleanup_summary(results)
    assert summary["total_targets"] == 3
    assert summary["success_count"] == 2
    assert summary["error_count"] == 1
    assert summary["canceled_count"] == 1
    assert summary["inactive_count"] == 1
