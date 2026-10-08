#!/bin/bash
# ==============================================================================
# 🚀 Obsidian AI Brain - AWS Lightsail / EC2 一键云端部署脚本
# 适用系统: Ubuntu 20.04 / 22.04 / 24.04 LTS
# ==============================================================================

set -e

echo "=========================================================="
echo "🌟 正在启动 Obsidian AI Brain 云端生产环境初始化..."
echo "=========================================================="

# 1. 切换时区为中国标准时间 (北京时间 UTC+8)
echo "⏰ [1/7] 设置系统时区为 Asia/Shanghai..."
sudo timedatectl set-timezone Asia/Shanghai

# 2. 检查并创建 2GB Swap 虚拟内存（防止 $3.5 1GB 内存突发 OOM）
if [ ! -f /swapfile ]; then
    echo "💾 [2/7] 未检测到 Swap，正在创建 2GB 虚拟内存以保障多模态与后台稳定..."
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "✅ 2GB Swap 激活成功！"
else
    echo "💾 [2/7] Swap 已存在，跳过创建。"
fi

# 3. 安装系统基础依赖与音视频工具 (ffmpeg 必须用于 Feynman Juicer)
echo "📦 [3/7] 更新软件源并安装基础系统库 (Python, rclone, ffmpeg, git)..."
sudo apt update -y
sudo apt install -y python3-pip python3-venv rclone ffmpeg git curl fuse3

# 允许非 root 用户挂载 fuse
if grep -q "#user_allow_other" /etc/fuse.conf 2>/dev/null; then
    sudo sed -i 's/#user_allow_other/user_allow_other/' /etc/fuse.conf
elif ! grep -q "user_allow_other" /etc/fuse.conf 2>/dev/null; then
    echo "user_allow_other" | sudo tee -a /etc/fuse.conf
fi

# 4. 挂载目录准备 (遵循严格无末尾空格规范)
CURRENT_USER=$(whoami)
BASE_DIR=$(cd "$(dirname "$0")/.." && pwd)
MOUNT_DIR="/mnt/gdrive/Obsidian/Knowledge Base"

echo "📁 [4/7] 检查并配置文件系统挂载点: /mnt/gdrive ..."
if mountpoint -q /mnt/gdrive 2>/dev/null; then
    echo "ℹ️ /mnt/gdrive 当前已处于挂载状态，跳过重复创建。"
else
    # 尝试清理可能残留的悬挂 FUSE 挂载
    sudo fusermount -u /mnt/gdrive 2>/dev/null || sudo umount -l /mnt/gdrive 2>/dev/null || true
    sudo mkdir -p /mnt/gdrive
    sudo chown -R "$CURRENT_USER":"$CURRENT_USER" /mnt/gdrive
    sudo chmod 775 /mnt/gdrive
fi

# 5. 配置 Python 独立虚拟环境与安装依赖
echo "🐍 [5/7] 配置虚拟环境并安装 Python 依赖..."
cd "$BASE_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. 配置 rclone 开机自启动 systemd 服务
echo "☁️ [6/7] 生成 rclone 云盘挂载系统服务..."
sudo tee /etc/systemd/system/rclone_obsidian.service > /dev/null <<EOF
[Unit]
Description=Rclone Mount Google Drive for Obsidian
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
ExecStart=/usr/bin/rclone mount gdrive: /mnt/gdrive \\
    --vfs-cache-mode writes \\
    --vfs-cache-max-age 24h \\
    --dir-cache-time 1m \\
    --allow-other \\
    --allow-non-empty \\
    --umask 002
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
echo "ℹ️ 如果尚未在 rclone config 中配置 'gdrive'，请在终端输入: rclone config"

# 7. 配置知识引擎 systemd 守护进程服务 (24/7 模式)
echo "🤖 [7/7] 生成知识引擎 systemd 守护服务 (obsidian_engine.service)..."
sudo tee /etc/systemd/system/obsidian_organizer.service > /dev/null <<EOF
[Unit]
Description=Obsidian AI Brain & AuraMemory Engine
After=network.target rclone_obsidian.service
Wants=rclone_obsidian.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$BASE_DIR
Environment=OBSIDIAN_BASE_PATH="$MOUNT_DIR"
Environment=PYTHONPATH="$BASE_DIR"
ExecStart=$BASE_DIR/venv/bin/python $BASE_DIR/src/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo "=========================================================="
echo "🎉 云端环境初始化完成！"
echo "=========================================================="
echo ""
echo "👉 后续启用指南（两种运行方式供选择）："
echo ""
echo "【方式一：全天候 24/7 守护进程（推荐）】"
echo "  1. 启动 rclone 挂载:       sudo systemctl enable --now rclone_obsidian"
echo "  2. 启动知识管理引擎:       sudo systemctl enable --now obsidian_organizer"
echo "  3. 查看引擎实时日志:       sudo journalctl -u obsidian_organizer -f"
echo "  * 优势: 支持手机端随时往 Telegram 发链接秒级自动提取；每日任务准时跑。"
echo ""
echo "【方式二：每日固定时间只跑一次（纯 Cron 批处理）】"
echo "  如果你不需要 24/7 监听 Inbox，只希望每天早晨 06:00 定时执行一次："
echo "  在终端输入: crontab -e"
echo "  添加以下行 (每天早晨 06:00 自动执行一次并生成复习/日报/看板):"
echo "  0 6 * * * cd $BASE_DIR && $BASE_DIR/venv/bin/python src/run_daily.py >> $BASE_DIR/AI\\ brain\\ log/cron.log 2>&1"
echo ""
