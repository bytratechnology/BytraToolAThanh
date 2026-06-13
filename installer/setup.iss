; Inno Setup — tao file cai dat Windows (.exe installer)
; Tai Inno Setup: https://jrsoftware.org/isinfo.php

#define MyAppName "Phần mềm tự động hoá"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Bytra"
#define MyAppExeName "Phần mềm tự động hoá.exe"

[Setup]
AppId={{B4E8F2A1-9C3D-4F1E-A2B8-7D6E5F4A3B2C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=PhanMemTuDongHoa_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tao shortcut tren Desktop"; GroupDescription: "Tuy chon:"

[Files]
Source: "..\dist\Phần mềm tự động hoá\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mo {#MyAppName}"; Flags: nowait postinstall skipifsilent
