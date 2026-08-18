@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Cognitive Debugger
cd /d "%~dp0src"
python -m cognitive_debugger.cli
