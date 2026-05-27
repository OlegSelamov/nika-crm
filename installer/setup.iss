[Setup]
AppName=Nika Business
AppVersion=1.0
DefaultDirName={pf}\Nika Business
DefaultGroupName=Nika Business
OutputDir=output
OutputBaseFilename=NikaBusinessSetup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Nika Business"; Filename: "{app}\start_local.bat"
Name: "{commondesktop}\Nika Business"; Filename: "{app}\start_local.bat"

[Run]
Filename: "{app}\start_local.bat"; Description: "Запустить Nika Business"; Flags: nowait postinstall skipifsilent