#define AppName "PDF para Markdown"
#define AppVersion "0.1.0"
#define AppExeName "PDF para Markdown.exe"

[Setup]
AppId={{DF08DCCE-8D44-48D3-BFBA-6BF30FB352BD}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
PrivilegesRequired=lowest
OutputDir=dist-installer
OutputBaseFilename=PDF-para-Markdown-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"

