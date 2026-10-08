import pytest
import datetime
from src.douyin_cleaner.auditor import (
    parse_relative_date,
    detect_canceled_profile,
)

def test_detect_canceled_profile():
    assert detect_canceled_profile("<div>该账号已注销，无法查看作品</div>") is True
    assert detect_canceled_profile("<p>用户已注销</p>") is True
    assert detect_canceled_profile("<div>该账号已被重置</div>") is True
    assert detect_canceled_profile("<div>正常用户的主页，粉丝数 1.2万</div>") is False

def test_parse_relative_date_absolute():
    base_date = datetime.date(2026, 9, 3)
    # 2026-01-01 -> 245 days
    dt_str, days = parse_relative_date("2026-01-01", base_date=base_date)
    assert dt_str == "2026-01-01"
    assert days == (base_date - datetime.date(2026, 1, 1)).days

def test_parse_relative_date_keywords():
    base_date = datetime.date(2026, 9, 3)
    _, days_yesterday = parse_relative_date("昨天 18:00", base_date=base_date)
    assert days_yesterday == 1

    _, days_3_days_ago = parse_relative_date("3天前", base_date=base_date)
    assert days_3_days_ago == 3

    _, days_1_month = parse_relative_date("2个月前", base_date=base_date)
    assert days_1_month >= 60

    _, days_1_year = parse_relative_date("1年前", base_date=base_date)
    assert days_1_year >= 365
