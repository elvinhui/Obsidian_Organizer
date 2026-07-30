# 🚀 Obsidian AI Brain - Telegram Bot 部署指南 (AWS Lightsail)

这份指南将教你如何将写好的 `telegram_bot.py` 部署到 AWS Lightsail (Ubuntu/Debian)，并挂载你的 Google Drive 以实现实时写入。

## 1. 挂载 Google Drive (rclone)

你需要让 Lightsail 能够读写你的 Google Drive，从而将数据同步到本地的 Obsidian。

1. **安装 rclone**:
   ```bash
   sudo -v ; curl https://rclone.org/install.sh | sudo bash
   ```
2. **配置 rclone**:
   ```bash
   rclone config
   ```
   - 按 `n` 新建配置，命名为 `gdrive`。
   - 选择 `drive` (通常是数字 18，Google Drive)。
   - `client_id` 和 `client_secret` 留空回车。
   - 权限选 `1` (Full access)。
   - 一直回车，遇到 `Use auto config?` 选择 `n` (因为你在服务器上)。
   - 它会给你一个链接，在你自己电脑的浏览器打开，登录 Google 账号授权，把得到的验证码粘贴回服务器终端。
   - 最后选 `y` 确认保存。

3. **创建挂载点并挂载**:
   ```bash
   sudo mkdir -p /mnt/gdrive
   sudo chown $USER:$USER /mnt/gdrive
   
   # 测试挂载 (前台运行，按 Ctrl+C 退出)
   rclone mount gdrive: /mnt/gdrive --vfs-cache-mode writes
   ```

4. **让 rclone 开机自动挂载**:
   创建系统服务文件：
   ```bash
   sudo nano /etc/systemd/system/rclone.service
   ```
   填入以下内容（注意把 `<你的用户名>` 换成你的 ubuntu 或 admin 用户名）：
   ```ini
   [Unit]
   Description=rclone mount
   After=network-online.target

   [Service]
   Type=simple
   User=<你的用户名>
   ExecStart=/usr/bin/rclone mount gdrive: /mnt/gdrive --vfs-cache-mode writes
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target
   ```
   保存后启动服务：
   ```bash
   sudo systemctl enable rclone
   sudo systemctl start rclone
   ```

## 2. 部署 Telegram Bot

1. 将 `lightsail_bot` 文件夹上传到服务器（例如放在 `~/lightsail_bot`）。
2. 在服务器上配置环境：
   ```bash
   cd ~/lightsail_bot
   sudo apt update && sudo apt install python3-pip python3-venv -y
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. 检查 `.env` 文件，确保配置无误：
   - `TELEGRAM_BOT_TOKEN` 是你在 BotFather 申请的 token
   - `GEMINI_API_KEY` 是你的 Gemini API 密钥
   - `INBOX_DIR` 路径正确（例如 `/mnt/gdrive/Obsidian/Knowledge Base/00 Inbox (收件箱)`）

## 3. 设置守护进程运行 (systemd)

为了让 Bot 断开 SSH 也能一直运行，且开机自启：

1. 编辑系统服务文件：
   ```bash
   sudo nano /etc/systemd/system/telegram_bot.service
   ```
2. 填入以下内容（确保路径和用户名一致，假设放在 `/home/ubuntu/lightsail_bot`）：
   ```ini
   [Unit]
   Description=Obsidian Telegram Bot
   After=network.target rclone.service

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/lightsail_bot
   ExecStart=/home/ubuntu/lightsail_bot/venv/bin/python telegram_bot.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
3. 启动 Bot 服务：
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable telegram_bot
   sudo systemctl start telegram_bot
   ```

## 4. 检查状态

查看 Bot 运行日志，如果没有报错，去 Telegram 给它发条消息测试吧！
```bash
sudo journalctl -u telegram_bot -f
```
