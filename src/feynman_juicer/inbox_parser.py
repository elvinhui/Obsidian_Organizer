import re
import os
import logging

logger = logging.getLogger(__name__)

# 匹配标准 http/https 链接
URL_PATTERN = re.compile(r'(https?://[^\s\>\]\)]+)')

class InboxParser:
    def __init__(self, filepath):
        self.filepath = filepath
        if not os.path.exists(filepath):
            # 兼容空文件或文件不存在
            open(filepath, 'a', encoding='utf-8').close()

    def get_pending_urls(self):
        """
        获取所有未带有 #已处理 或 #Failed 标签的链接
        """
        with open(self.filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        pending = []
        for i, line in enumerate(lines):
            if '#已处理' in line or '#Failed' in line:
                continue
            match = URL_PATTERN.search(line)
            if match:
                url = match.group(1)
                pending.append({
                    "line_idx": i,
                    "url": url,
                    "original_line": line.strip()
                })
        return pending

    def mark_status(self, line_idx, status_tag):
        """
        将指定行的状态标记为 status_tag (如 '#已处理' 或 '#Failed')
        """
        with open(self.filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        if line_idx < len(lines):
            line = lines[line_idx].rstrip('\n')
            if status_tag not in line:
                lines[line_idx] = line + f" {status_tag}\n"
                logger.info(f"Marked line {line_idx} with {status_tag}")
                
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test script
    test_file = "test_inbox.md"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("- [ ] 看看这个视频 https://v.douyin.com/idqX9W52/\n")
        f.write("- [ ] B站好文 https://www.bilibili.com/video/BV1xx411c7mD #已处理\n")
        
    parser = InboxParser(test_file)
    urls = parser.get_pending_urls()
    print("Pending:", urls)
    if urls:
        parser.mark_status(urls[0]['line_idx'], "#Failed")
    print("After mark:", parser.get_pending_urls())
    os.remove(test_file)
