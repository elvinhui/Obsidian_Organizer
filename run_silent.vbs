Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\KATANA 17 B13V\Documents\projects\Obsidianorganizer"
WshShell.Run """C:\Users\KATANA 17 B13V\AppData\Local\Python\pythoncore-3.14-64\python.exe"" src/main.py", 0, False
