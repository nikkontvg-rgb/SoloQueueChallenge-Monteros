#define MyAppName "SoloQ Challenge Monteros - Agente"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Organizacion SoloQ Challenge Monteros"
#define MyAppExeName "SoloQChallengeAgente.exe"

[Setup]
AppId={{7D4CBB20-8D36-48CF-9E1B-2A9910C65E77}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SoloQChallengeMonteros
DefaultGroupName=SoloQ Challenge Monteros
OutputDir=..\dist-installer
OutputBaseFilename=Instalador_SoloQChallenge_Monteros
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\SoloQChallengeAgente.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SoloQ Challenge Monteros"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\SoloQ Challenge Monteros"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir SoloQ Challenge Monteros"; Flags: postinstall nowait skipifsilent
