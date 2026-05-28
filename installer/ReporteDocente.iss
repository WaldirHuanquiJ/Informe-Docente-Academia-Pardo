; Inno Setup Script - Reporte Docente

#define MyAppName "Reporte Docente"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Fis: Waldir Huanque J."
#define MyAppAuthor "Fis: Waldir Huanque J."
#define MyAppExeName "ReporteDocente.exe"

[Setup]
AppId={{D6F1DCA0-8E2B-4B9A-8F2E-1E9A8D35C041}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://example.com
AppSupportURL=https://example.com/soporte
AppUpdatesURL=https://example.com/actualizaciones
AppComments=Sistema para analisis, exportacion e impresion de asistencia docente.
AppContact=Autor: {#MyAppAuthor}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=Instalador_Reporte_Docente
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
SetupIconFile=..\img\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=licencia.txt
InfoBeforeFile=antes_de_instalar.txt
InfoAfterFile=despues_de_instalar.txt
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Instalador de {#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\ReporteDocente\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

