Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\Apps\whisper-writer"
WshShell.Run "cmd /c call .\venv_py311\Scripts\activate && pythonw run.py", 0, False