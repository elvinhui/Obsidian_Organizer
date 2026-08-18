Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\KATANA 17 B13V\Documents\projects\Obsidianorganizer"
WshShell.Run "python src/main.py", 0, False
