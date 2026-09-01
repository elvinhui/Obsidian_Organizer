#!/bin/bash

# Ensure we are in the right directory
cd /home/ubuntu/Obsidian_Organizer

echo "🚀 Installing Playwright dependencies for headless execution..."
source lightsail_bot/venv/bin/activate
pip install playwright
playwright install chromium --with-deps

echo "⏰ Configuring Cron Job for 3:00 AM..."
# We will check if it's already in crontab to avoid duplicates
CRON_JOB="0 3 * * * cd /home/ubuntu/Obsidian_Organizer && /home/ubuntu/Obsidian_Organizer/lightsail_bot/venv/bin/python lightsail_bot/algo_tamer.py >> /home/ubuntu/Obsidian_Organizer/lightsail_bot/logs/cron.log 2>&1"

(crontab -l 2>/dev/null | grep -Fv "algo_tamer.py"; echo "$CRON_JOB") | crontab -

echo "✅ Done! Algo Tamer will now run automatically at 3:00 AM daily."
echo "Note: If your server timezone is UTC (default), this will run at 3:00 AM UTC (11:00 AM Beijing Time)."
echo "To set your server to Beijing Time, run: sudo timedatectl set-timezone Asia/Shanghai"
