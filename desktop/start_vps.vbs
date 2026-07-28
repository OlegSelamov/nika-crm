Set shell = CreateObject("WScript.Shell")

command = "cmd /c cd /d ""D:\PRO\nika_business\desktop"" && ""C:\Program Files\nodejs\npm.cmd"" run vps"

shell.Run command, 0, False