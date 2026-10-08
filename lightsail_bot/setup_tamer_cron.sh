#!/bin/bash

# Determine directory dynamically
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Check if algo_tamer.py is directly in SCRIPT_DIR or in a subdirectory
if [ -f "$SCRIPT_DIR/algo_tamer.py" ]; then
    BASE_DIR="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/lightsail_bot/algo_tamer.py" ]; then
    BASE_DIR="$SCRIPT_DIR/lightsail_bot"
else
    echo "❌ Cannot find algo_tamer.py in $SCRIPT_DIR"
    exit 1
fi

VENV_PYTHON="$BASE_DIR/venv/bin/python"
LOGS_DIR="$BASE_DIR/logs"
mkdir -p "$LOGS_DIR"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "⚠️ venv python not found at $VENV_PYTHON. Checking /home/ubuntu/lightsail_bot/venv/bin/python..."
    if [ -f "/home/ubuntu/lightsail_bot/venv/bin/python" ]; then
        VENV_PYTHON="/home/ubuntu/lightsail_bot/venv/bin/python"
    else
        VENV_PYTHON="$(which python3)"
    fi
fi

echo "🚀 Installing Playwright dependencies for headless execution..."
if [ -f "$BASE_DIR/venv/bin/activate" ]; then
    source "$BASE_DIR/venv/bin/activate"
fi
pip install playwright playwright-stealth
playwright install chromium --with-deps

echo "⏰ Configuring Cron Job for 3:00 AM..."
CRON_JOB="0 3 * * * cd $BASE_DIR && $VENV_PYTHON algo_tamer.py >> $LOGS_DIR/cron.log 2>&1"

(crontab -l 2>/dev/null | grep -Fv "algo_tamer.py"; echo "$CRON_JOB") | crontab -

echo "✅ Done! Algo Tamer cron job has been configured:"
echo "   $CRON_JOB"
echo "Note: If your server timezone is UTC, 3:00 AM UTC is 11:00 AM Beijing Time."
echo "To set your server to Beijing Time, run: sudo timedatectl set-timezone Asia/Shanghai"
