Set WshShell = CreateObject("WScript.Shell")
' Run python juicer_daemon.py silently without keeping the black console window open
WshShell.Run "python juicer_daemon.py", 0, False
