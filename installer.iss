#define MyAppName "Paladium Desktop"
#define MyAppVersion "0.2"
#define MyAppExeName "PaladiumDesktop.exe"

[Setup]
AppId={{1E4D1A49-3B7F-4C7A-9E19-5B1A6B4B8F63}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=Output
OutputBaseFilename=PaladiumDesktop-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\PaladiumDesktop\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
