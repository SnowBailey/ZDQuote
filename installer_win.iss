; ZDQuote · Inno Setup 安装包脚本
; 前置：安装 Inno Setup（https://jrsoftware.org/isinfo.php，免费）
; 用法：用 Inno Setup 打开本文件 -> Build -> 编译
; 产物：installer\ZDQuote_Setup.exe
;
; 编译前请先运行 build_win.bat 生成 dist\ZDQuote\ 目录

#define MyAppName "ZDQuote 报价助手"
#define MyAppVersion "1.0"
#define MyAppPublisher "ZDQuote"
#define MyAppURL "https://example.com"
#define MyAppExeName "ZDQuote.exe"

[Setup]
; 注：AppId 是卸载与升级的唯一标识，请勿随意更改
AppId={{3CA513B9-97EF-45D6-8F94-164AE9874E9D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; 安装包图标
SetupIconFile=ZDQuote.ico
; 生成的安装程序
OutputDir=installer
OutputBaseFilename=ZDQuote_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 64 位系统装到 Program Files；普通用户也会请求 UAC
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
; 中文界面（Inno Setup 6 自带 Chinese.isl）
WizardResizable=yes

[Languages]
; 为兼容各种 Inno Setup 分发版，使用内置且一定存在的 Default.isl（英文界面）。
; 若本地有 ChineseSimplified.isl，可取消下面注释并注释掉 english 行。
Name: "english"; MessagesFile: "compiler:Default.isl"
; Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
; 把 PyInstaller 产出的整个文件夹原样打进安装包
Source: "dist\ZDQuote\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
