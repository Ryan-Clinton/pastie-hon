; Inno Setup script for PastieSetup-<version>.exe.
;
;     iscc /DVersion=0.3.0 packaging\pastie.iss
;
; Built by .github/workflows/release.yml from the PyInstaller folder in
; build\pkg\dist\Pastie. Per-user, no administrator prompt: Pastie runs as the
; person signed in (the service is a login task, not a Windows service), so
; installing it machine-wide would promise something it does not do.
;
; Uninstalling leaves %PROGRAMDATA%\Pastie alone - settings, the encrypted
; password and what Pastie remembers. `pastie where` shows it; deleting
; somebody's settings is theirs to decide.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6F1F3C2A-8B3E-4F7B-9C55-7A1D3E0B9A42}
AppName=Pastie
AppVersion={#Version}
AppVerName=Pastie {#Version}
AppPublisher=Pastie contributors (unofficial - not affiliated with Haier)
AppPublisherURL=https://github.com/Ryan-Clinton/pastie-hon
AppSupportURL=https://github.com/Ryan-Clinton/pastie-hon/issues
DefaultDirName={localappdata}\Programs\Pastie
DefaultGroupName=Pastie
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\pkg\installer
OutputBaseFilename=PastieSetup-{#Version}
SetupIconFile=..\assets\pastie.ico
UninstallDisplayIcon={app}\Pastie.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Put Pastie on the Desktop"; Flags: unchecked
Name: "startup"; Description: "Watch the appliance whenever I sign in (recommended - otherwise nothing is watching unless the window is open)"

[Files]
Source: "..\build\pkg\dist\Pastie\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Pastie"; Filename: "{app}\Pastie.exe"; Comment: "What your Haier appliance is doing"
Name: "{userdesktop}\Pastie"; Filename: "{app}\Pastie.exe"; Tasks: desktopicon
Name: "{userstartup}\Pastie service"; Filename: "{app}\Pastie.exe"; Parameters: "service"; Tasks: startup

[Run]
Filename: "{app}\Pastie.exe"; Description: "Open Pastie"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; The service is Pastie.exe running with an argument. Stop it, or the files it
; holds open cannot be removed.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Pastie.exe"; Flags: runhidden; RunOnceId: "StopPastie"
