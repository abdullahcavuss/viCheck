; viCheck installer (Inno Setup 6, https://jrsoftware.org/isinfo.php)
; Built by build.bat after PyInstaller:  ISCC.exe /DAppVersion=1.0.0 installer\viCheck.iss
; Output: dist\viCheck-Setup-<version>.exe
;
; - Installs for the current user without administrator rights (the setup offers "all users" too).
; - Start menu shortcut, optional desktop shortcut, entry in "Installed apps" with an uninstaller.
; - Settings and cache (%LOCALAPPDATA%\viCheck) are kept when uninstalling.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "viCheck"
#define AppExe "viCheck.exe"

[Setup]
AppId={{6C1E0F4B-3A7D-4C55-9E2B-8D2F1A9C7E31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=abdullahcavuss
AppPublisherURL=https://github.com/abdullahcavuss/viCheck
AppSupportURL=https://github.com/abdullahcavuss/viCheck/issues
AppComments=LabVIEW VI and folder comparison
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
SetupIconFile=..\static\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=viCheck-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; the whole PyInstaller folder: viCheck.exe + _internal\
Source: "..\dist\viCheck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; an update replaces the bundled Python files completely (no stale modules from an older version)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "LabVIEW VI and folder comparison"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
