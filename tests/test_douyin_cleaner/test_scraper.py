import pytest
from src.douyin_cleaner.scraper import parse_following_response_data

def test_parse_following_response_data():
    raw_api_payload = {
        "status_code": 0,
        "has_more": 1,
        "followings": [
            {
                "sec_uid": "MS4wLjABAAAA12345",
                "uid": "10001",
                "short_id": "9999",
                "nickname": "科技前沿",
                "signature": "分享前沿AI技术",
                "avatar_thumb": {
                    "url_list": ["https://p3.douyinpic.com/avatar1.jpg"]
                },
                "follower_status": 1
            },
            {
                "sec_uid": "MS4wLjABAAAA67890",
                "uid": "10002",
                "nickname": "已注销用户",
                "signature": "",
                "avatar_168x168": {
                    "url_list": ["https://p3.douyinpic.com/avatar2.jpg"]
                },
                "follower_status": 0
            }
        ]
    }
    
    users = parse_following_response_data(raw_api_payload)
    assert len(users) == 2
    assert users[0]["sec_uid"] == "MS4wLjABAAAA12345"
    assert users[0]["nickname"] == "科技前沿"
    assert users[0]["avatar"] == "https://p3.douyinpic.com/avatar1.jpg"
    assert users[1]["nickname"] == "已注销用户"
    assert users[1]["avatar"] == "https://p3.douyinpic.com/avatar2.jpg"

def test_parse_empty_or_invalid_payload():
    assert parse_following_response_data({}) == []
    assert parse_following_response_data({"status_code": 0}) == []
    assert parse_following_response_data({"followings": "invalid"}) == []
