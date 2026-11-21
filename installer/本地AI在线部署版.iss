; 本地AI（在线部署版）V7 安装脚本
; 本安装包仅包含软件本体（主程序 + 界面 + 说明 + 声明），
; 不含 Ollama 运行环境，也不含任何模型文件，均由软件首次启动时联网下载。

[Setup]
AppName=本地AI（在线部署版）
AppVersion=7.0.0
AppVerName=本地AI（在线部署版）V7
AppPublisher=折**
AppCopyright=Copyright (C) 2026 折**
AppId={{8F3C21A4-7B52-4C6E-9E31-4C7D9A61B2E5}
DefaultDirName=C:\本地AI在线部署版
DefaultGroupName=本地AI
DisableProgramGroupPage=yes
LicenseFile=src\body\软件版权声明_产品版.txt
OutputDir=交付
OutputBaseFilename=本地AI_在线部署版_安装包_V7_2026-11-13
SetupIconFile=src\app.ico
UninstallDisplayIcon={app}\本地AI.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion=7.0.0.0
VersionInfoProductName=本地AI（在线部署版）
VersionInfoProductVersion=7.0.0
VersionInfoCompany=折**
VersionInfoCopyright=Copyright (C) 2026 折**
VersionInfoDescription=本地AI（在线部署版）安装程序 V7

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
; 桌面快捷方式改为强制创建（见 [Icons]），不再提供可取消的选项

[InstallDelete]
; 清掉旧版在公共桌面留下的重复快捷方式，确保桌面上只有一个图标
Type: files; Name: "{autodesktop}\本地AI.lnk"

[Files]
Source: "build\dist\本地AI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "src\body\使用说明.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "src\body\软件版权声明_产品版.txt"; DestName: "软件版权声明.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "src\app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "src\body\清理临时文件.ps1"; DestDir: "{app}\工具"; Flags: ignoreversion

[Icons]
Name: "{group}\本地AI"; Filename: "{app}\本地AI.exe"; IconFilename: "{app}\app.ico"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{group}\卸载 本地AI"; Filename: "{uninstallexe}"
; 桌面快捷方式只建一个：当前登录用户的桌面
; （旧版同时在公共桌面建过一个，下面的 [InstallDelete] 会把那个清掉，避免出现两个图标）
Name: "{userdesktop}\本地AI"; Filename: "{app}\本地AI.exe"; IconFilename: "{app}\app.ico"

[Run]
Filename: "{app}\本地AI.exe"; Description: "立即启动 本地AI"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_setup_tmp"
