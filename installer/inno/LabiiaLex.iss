; LabiiaLex Windows Installer (single-file wizard)
; Build example:
;   iscc /DSourceDir="C:\path\to\stage" /DAppVersion="1.0.8" installer\inno\LabiiaLex.iss

#ifndef SourceDir
  #define SourceDir "..\\..\\dist\\LabiiaLex"
#endif

#ifndef AppVersion
  #define AppVersion "1.0.8"
#endif

#ifndef SetupOutputDir
  #define SetupOutputDir "..\\dist"
#endif

#ifndef GephiRunnerSHA256
  #define GephiRunnerSHA256 ""
#endif

[Setup]
AppId={{4DE6D54E-3283-4CFA-8F42-2717E7DF4D74}
AppName=<labiia_lex>
AppVersion={#AppVersion}
AppPublisher=labiia_lex
AppPublisherURL=https://github.com/cardososampaio/labiia_lex
AppSupportURL=https://github.com/cardososampaio/labiia_lex/issues
AppUpdatesURL=https://github.com/cardososampaio/labiia_lex
DefaultDirName={localappdata}\Programs\LabiiaLex
DisableDirPage=no
DefaultGroupName=labiia_lex
AllowNoIcons=yes
LicenseFile={#SourceDir}\license.txt
OutputDir={#SetupOutputDir}
OutputBaseFilename=labiia_lex-Setup-x64-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\LabiiaLex.exe
SetupLogging=yes

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Dirs]
Name: "{localappdata}\LabiiaLex"
Name: "{localappdata}\LabiiaLex\logs"
Name: "{localappdata}\LabiiaLex\backup"
Name: "{localappdata}\LabiiaLex\R"
Name: "{localappdata}\LabiiaLex\R\library"

[Files]
Source: "{#SourceDir}\installer\scripts\check_r.ps1"; Flags: dontcopy
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\labiia_lex\labiia_lex"; Filename: "{app}\LabiiaLex.exe"
Name: "{autoprograms}\labiia_lex\Reparar pacotes R do labiia_lex"; Filename: "{app}\LabiiaLex.exe"; Parameters: "--repair-r-packages"; WorkingDir: "{app}"
Name: "{autodesktop}\labiia_lex"; Filename: "{app}\LabiiaLex.exe"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\LabiiaLex"

[Code]
var
  RScriptPath: string;
  DetectedRVersion: string;
  RInstallLogPath: string;
  RInstallStatePath: string;
  RLibsUserPath: string;
  SelfTestJsonPath: string;
  LexiDataRoot: string;
  LogsRoot: string;
  TempFileSeq: Integer;
  LastProvisioningError: string;
  PostInstallWarnings: string;
  RCheckPage: TWizardPage;
  RCheckIntroLabel: TNewStaticText;
  RCheckStatusLabel: TNewStaticText;
  RCheckDetailsLabel: TNewStaticText;
  RCheckRetryButton: TNewButton;
  RCheckOpenSiteButton: TNewButton;
  RCheckJsonPath: string;
  RCheckScriptPath: string;
  RCheckOk: Boolean;
  RCheckCranReachable: Boolean;
  RCheckSource: string;
  RCheckMessage: string;
  RCheckDownloadUrl: string;

function RunRPrereqCheck(): Boolean;
  forward;

function IsDigit(const Ch: Char): Boolean;
begin
  Result := (Ch >= '0') and (Ch <= '9');
end;

procedure SetProvisioningError(const Msg: string);
begin
  LastProvisioningError := Msg;
  Log('Provisioning error: ' + Msg);
end;

procedure AddPostInstallWarning(const Reason: string);
var
  FullReason: string;
begin
  FullReason := Reason;
  if LastProvisioningError <> '' then
    FullReason := FullReason + #13#10 + LastProvisioningError;

  if PostInstallWarnings <> '' then
    PostInstallWarnings := PostInstallWarnings + #13#10 + #13#10;
  PostInstallWarnings := PostInstallWarnings + FullReason;
  Log('Post-install warning: ' + FullReason);
end;

procedure ShowPostInstallWarnings();
begin
  if PostInstallWarnings = '' then
    Exit;

  SuppressibleMsgBox(
    'O labiia_lex foi instalado, mas uma validacao automatica indicou pendencia:' + #13#10 + #13#10 +
    PostInstallWarnings + #13#10 + #13#10 +
    'Como resolver:' + #13#10 +
    '1. Confirme que este computador esta conectado a internet.' + #13#10 +
    '2. Abra o atalho "Reparar pacotes R do labiia_lex" no Menu Iniciar.' + #13#10 +
    '3. Se precisar de suporte, envie os logs desta pasta:' + #13#10 +
    LogsRoot,
    mbInformation,
    MB_OK,
    IDOK
  );
end;

function StripQuotes(const Value: string): string;
begin
  Result := Trim(Value);
  if (Length(Result) >= 2) and (Result[1] = '"') and (Result[Length(Result)] = '"') then
    Result := Copy(Result, 2, Length(Result) - 2);
end;

function PopFirstLine(var Text: string): string;
var
  P: Integer;
begin
  P := Pos(#10, Text);
  if P > 0 then
  begin
    Result := Trim(Copy(Text, 1, P - 1));
    Delete(Text, 1, P);
  end
  else
  begin
    Result := Trim(Text);
    Text := '';
  end;
end;

function CaptureCommandOutput(const CommandLine: string; var Output: string): Boolean;
var
  TempFile: string;
  Params: string;
  ResultCode: Integer;
  Lines: TArrayOfString;
  i: Integer;
begin
  TempFileSeq := TempFileSeq + 1;
  TempFile := ExpandConstant('{tmp}\labiialex_cmd_' + IntToStr(TempFileSeq) + '.log');
  Params := '/C ' + CommandLine + ' > "' + TempFile + '" 2>&1';

  Result := Exec(
    ExpandConstant('{cmd}'),
    Params,
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );

  Output := '';
  if FileExists(TempFile) then
  begin
    if LoadStringsFromFile(TempFile, Lines) then
    begin
      for i := 0 to GetArrayLength(Lines) - 1 do
      begin
        if Output <> '' then
          Output := Output + #13#10;
        Output := Output + Lines[i];
      end;
      Output := Trim(Output);
    end;
    DeleteFile(TempFile);
  end;

  Result := Result and (ResultCode = 0);
end;

function ProbeCommandExecutable(const ExePath: string; const Params: string): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(
    ExePath,
    Params,
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0);
end;

function RunVersionProbe(const ExePath: string; const Params: string; var Output: string): Boolean;
var
  CommandLine: string;
begin
  CommandLine := '"' + ExePath + '"';
  if Params <> '' then
    CommandLine := CommandLine + ' ' + Params;
  Result := CaptureCommandOutput(CommandLine, Output);
end;

function ExtractFirstVersionToken(const Raw: string): string;
var
  i, StartPos: Integer;
begin
  Result := '';
  StartPos := 0;
  for i := 1 to Length(Raw) do
  begin
    if IsDigit(Raw[i]) then
    begin
      StartPos := i;
      Break;
    end;
  end;
  if StartPos = 0 then
    Exit;

  i := StartPos;
  while i <= Length(Raw) do
  begin
    if IsDigit(Raw[i]) or (Raw[i] = '.') or (Raw[i] = '_') then
      Result := Result + Raw[i]
    else
      Break;
    i := i + 1;
  end;
end;

procedure ParseVersionToken(const Token: string; var Major: Integer; var Minor: Integer; var Patch: Integer);
var
  Work: string;
  Part: string;
  DotPos: Integer;
  Index: Integer;
begin
  Major := 0;
  Minor := 0;
  Patch := 0;

  Work := Token;
  StringChangeEx(Work, '_', '.', True);
  Index := 0;

  while Work <> '' do
  begin
    DotPos := Pos('.', Work);
    if DotPos > 0 then
    begin
      Part := Copy(Work, 1, DotPos - 1);
      Delete(Work, 1, DotPos);
    end
    else
    begin
      Part := Work;
      Work := '';
    end;

    Index := Index + 1;
    if Index = 1 then
      Major := StrToIntDef(Part, 0)
    else if Index = 2 then
      Minor := StrToIntDef(Part, 0)
    else if Index = 3 then
    begin
      Patch := StrToIntDef(Part, 0);
      Break;
    end;
  end;
end;

function CompareVersionTokens(const LeftToken: string; const RightToken: string): Integer;
var
  LeftMajor, LeftMinor, LeftPatch: Integer;
  RightMajor, RightMinor, RightPatch: Integer;
begin
  ParseVersionToken(LeftToken, LeftMajor, LeftMinor, LeftPatch);
  ParseVersionToken(RightToken, RightMajor, RightMinor, RightPatch);

  if LeftMajor > RightMajor then
    Result := 1
  else if LeftMajor < RightMajor then
    Result := -1
  else if LeftMinor > RightMinor then
    Result := 1
  else if LeftMinor < RightMinor then
    Result := -1
  else if LeftPatch > RightPatch then
    Result := 1
  else if LeftPatch < RightPatch then
    Result := -1
  else
    Result := 0;
end;

function VersionTokenAtLeast(const Token: string; const Minimum: string): Boolean;
begin
  Result := CompareVersionTokens(Token, Minimum) >= 0;
end;

function MajorMinorVersionToken(const Token: string): string;
var
  Major: Integer;
  Minor: Integer;
  Patch: Integer;
begin
  ParseVersionToken(Token, Major, Minor, Patch);
  Result := IntToStr(Major) + '.' + IntToStr(Minor);
end;

function FirstExistingPathFromOutput(const Raw: string): string;
var
  Work: string;
  Line: string;
begin
  Result := '';
  Work := Raw;
  StringChangeEx(Work, #13, '', True);

  while Work <> '' do
  begin
    Line := StripQuotes(PopFirstLine(Work));
    if (Line <> '') and FileExists(Line) then
    begin
      Result := Line;
      Exit;
    end;
  end;
end;

function FindRInRegistry(const Root: Integer; const SubKey: string): string;
var
  InstallPath: string;
  Candidate: string;
begin
  Result := '';

  if RegQueryStringValue(Root, SubKey, 'InstallPath', InstallPath) then
  begin
    Candidate := AddBackslash(InstallPath) + 'bin\Rscript.exe';
    if FileExists(Candidate) and ProbeCommandExecutable(Candidate, '--version') then
    begin
      Result := Candidate;
      Exit;
    end;

    Candidate := AddBackslash(InstallPath) + 'bin\x64\Rscript.exe';
    if FileExists(Candidate) and ProbeCommandExecutable(Candidate, '--version') then
    begin
      Result := Candidate;
      Exit;
    end;
  end;
end;

function FindNewestRInRoot(const RootPath: string): string;
var
  FindRec: TFindRec;
  Candidate: string;
  VersionToken: string;
  BestVersion: string;
  BestPath: string;
begin
  Result := '';
  if not DirExists(RootPath) then
    Exit;

  BestVersion := '';
  BestPath := '';

  if FindFirst(AddBackslash(RootPath) + 'R-*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          VersionToken := Copy(FindRec.Name, 3, MaxInt);
          if VersionToken = '' then
            VersionToken := '0.0.0';

          Candidate := AddBackslash(AddBackslash(RootPath) + FindRec.Name) + 'bin\Rscript.exe';
          if FileExists(Candidate) and ProbeCommandExecutable(Candidate, '--version') then
          begin
            if (BestPath = '') or (CompareVersionTokens(VersionToken, BestVersion) > 0) then
            begin
              BestPath := Candidate;
              BestVersion := VersionToken;
            end;
          end;

          Candidate := AddBackslash(AddBackslash(RootPath) + FindRec.Name) + 'bin\x64\Rscript.exe';
          if FileExists(Candidate) and ProbeCommandExecutable(Candidate, '--version') then
          begin
            if (BestPath = '') or (CompareVersionTokens(VersionToken, BestVersion) > 0) then
            begin
              BestPath := Candidate;
              BestVersion := VersionToken;
            end;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;

  Result := BestPath;
end;

function FindRFromWhere(): string;
var
  Output: string;
  Candidate: string;
begin
  Result := '';
  if CaptureCommandOutput('where Rscript', Output) then
  begin
    Candidate := FirstExistingPathFromOutput(Output);
    if (Candidate <> '') and ProbeCommandExecutable(Candidate, '--version') then
      Result := Candidate;
  end;
end;

function FindRScriptExecutable(): string;
var
  Candidate: string;
begin
  Result := '';

  Candidate := FindRInRegistry(HKLM64, 'SOFTWARE\R-core\R');
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindRInRegistry(HKLM64, 'SOFTWARE\R-core\R64');
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindRInRegistry(HKLM, 'SOFTWARE\R-core\R');
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindRInRegistry(HKLM, 'SOFTWARE\R-core\R64');
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindRInRegistry(HKCU, 'SOFTWARE\R-core\R');
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindRInRegistry(HKCU, 'SOFTWARE\R-core\R64');
  if Candidate <> '' then begin Result := Candidate; Exit; end;

  Candidate := FindNewestRInRoot(ExpandConstant('{commonpf}\R'));
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindNewestRInRoot(ExpandConstant('{commonpf32}\R'));
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindNewestRInRoot(ExpandConstant('{localappdata}\Programs\R'));
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindNewestRInRoot(ExpandConstant('{localappdata}\R'));
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindNewestRInRoot('C:\R');
  if Candidate <> '' then begin Result := Candidate; Exit; end;
  Candidate := FindNewestRInRoot('C:\tools\R');
  if Candidate <> '' then begin Result := Candidate; Exit; end;

  Candidate := FindRFromWhere();
  if Candidate <> '' then begin Result := Candidate; Exit; end;
end;


function IsRVersionSupported(var VersionText: string): Boolean;
var
  Token: string;
  CheckParams: string;
  PathRTagPos: Integer;
  PathTail: string;
begin
  VersionText := '';
  if RunVersionProbe(RScriptPath, '--version', VersionText) then
  begin
    Token := ExtractFirstVersionToken(VersionText);
    if Token <> '' then
    begin
      Result := VersionTokenAtLeast(Token, '4.0.0');
      Exit;
    end;
  end;

  { Fallback 1: extrai versao do path, ex.: ...\R-4.5.1\bin\Rscript.exe }
  PathRTagPos := Pos('\R-', Uppercase(RScriptPath));
  if PathRTagPos > 0 then
  begin
    PathTail := Copy(RScriptPath, PathRTagPos + 3, MaxInt);
    Token := ExtractFirstVersionToken(PathTail);
    if Token <> '' then
    begin
      VersionText := Token;
      Result := VersionTokenAtLeast(Token, '4.0.0');
      Exit;
    end;
  end;

  { Fallback 2: valida diretamente no R e usa apenas exit code }
  CheckParams := '--vanilla -e "q(status=if (getRversion() >= ''4.0.0'') 0 else 1)"';
  if ProbeCommandExecutable(RScriptPath, CheckParams) then
  begin
    VersionText := '4.0+';
    Result := True;
    Exit;
  end;

  Result := False;
end;


function CheckCRANConnectivity(): Boolean;
var
  ResultCode: Integer;
  Cmd: string;
begin
  Cmd := '$ProgressPreference=''SilentlyContinue''; try { Invoke-WebRequest -UseBasicParsing -Uri "https://cloud.r-project.org" -Method Head -TimeoutSec 20 | Out-Null; exit 0 } catch { exit 1 }';
  Result := Exec(
    'powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "' + Cmd + '"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0);
end;


function ResolveBundlePath(const RelativePath: string): string;
var
  DirectPath: string;
  InternalPath: string;
begin
  DirectPath := ExpandConstant('{app}\' + RelativePath);
  InternalPath := ExpandConstant('{app}\_internal\' + RelativePath);

  if FileExists(DirectPath) or DirExists(DirectPath) then
  begin
    Result := DirectPath;
    Exit;
  end;

  if FileExists(InternalPath) or DirExists(InternalPath) then
  begin
    Result := InternalPath;
    Exit;
  end;

  Result := DirectPath;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  Log('PrepareToInstall: inicio');

  if not IsWin64 then
  begin
    Result := 'O instalador do labiia_lex requer Windows 64-bit.';
    Exit;
  end;

  LexiDataRoot := ExpandConstant('{localappdata}\LabiiaLex');
  LogsRoot := AddBackslash(LexiDataRoot) + 'logs';

  ForceDirectories(LogsRoot);

  Log('PrepareToInstall: validando R externo obrigatorio');
  if not RunRPrereqCheck() then
  begin
    Result := RCheckMessage;
    if Result = '' then
      Result := 'O labiia_lex requer o R instalado neste computador.';
    Exit;
  end;

  RLibsUserPath := AddBackslash(LexiDataRoot) + 'R\library\' + MajorMinorVersionToken(ExtractFirstVersionToken(DetectedRVersion));
  ForceDirectories(RLibsUserPath);

  Log('R detectado: ' + RScriptPath + ' | versao: ' + Trim(DetectedRVersion));
  Log('Biblioteca R do labiia_lex: ' + RLibsUserPath);
  Log('PrepareToInstall: fim');
end;


function RunRPackageProvisioning(): Boolean;
var
  ResultCode: Integer;
  ScriptPath: string;
  CoreManifest: string;
  OptionalManifest: string;
  LockManifest: string;
  Params: string;
begin
  Result := False;
  LastProvisioningError := '';

  ScriptPath := ExpandConstant('{app}\installer\scripts\install_r_packages.R');
  CoreManifest := ExpandConstant('{app}\installer\manifests\r_packages_core.json');
  OptionalManifest := ExpandConstant('{app}\installer\manifests\r_packages_optional.json');
  LockManifest := ExpandConstant('{app}\installer\manifests\r_environment_lock.json');
  RInstallLogPath := AddBackslash(LogsRoot) + 'r_package_install.log';
  RInstallStatePath := AddBackslash(LexiDataRoot) + 'r_install_state.json';

  if not FileExists(ScriptPath) then
  begin
    SetProvisioningError('Script de provisionamento R nao encontrado: ' + ScriptPath);
    Exit;
  end;
  if not FileExists(CoreManifest) then
  begin
    SetProvisioningError('Manifesto core de pacotes R nao encontrado: ' + CoreManifest);
    Exit;
  end;
  if not FileExists(OptionalManifest) then
  begin
    SetProvisioningError('Manifesto opcional de pacotes R nao encontrado: ' + OptionalManifest);
    Exit;
  end;
  if not FileExists(LockManifest) then
  begin
    SetProvisioningError('Lock de ambiente R nao encontrado: ' + LockManifest);
    Exit;
  end;

  if (RScriptPath = '') or (not FileExists(RScriptPath)) then
  begin
    if not RunRPrereqCheck() then
    begin
      SetProvisioningError(RCheckMessage);
      Exit;
    end;
  end;
  if (RScriptPath = '') or (not FileExists(RScriptPath)) then
  begin
    SetProvisioningError('Rscript.exe nao encontrado.');
    Exit;
  end;

  if not IsRVersionSupported(DetectedRVersion) then
  begin
    SetProvisioningError('Runtime R encontrado, mas versao incompativel. Requerido: R 4.0+.');
    Exit;
  end;

  Params :=
    '"' + ScriptPath + '" ' +
    '"' + CoreManifest + '" ' +
    '"' + OptionalManifest + '" ' +
    '"' + RInstallLogPath + '" ' +
    '"' + RInstallStatePath + '" ' +
    '"' + RLibsUserPath + '" ' +
    '"https://cloud.r-project.org" ' +
    '"' + LockManifest + '"';

  Log('Running R package provisioning: ' + RScriptPath + ' ' + Params);

  Result := Exec(
    RScriptPath,
    Params,
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0);

  if not Result then
  begin
    Log('R package provisioning failed. ExitCode=' + IntToStr(ResultCode));
    SetProvisioningError('Falha ao instalar pacotes R. Verifique: ' + RInstallLogPath);
  end;
end;


function NormalizeForJsonSearch(const Raw: string): string;
begin
  Result := Lowercase(Raw);
  StringChangeEx(Result, ' ', '', True);
  StringChangeEx(Result, #13, '', True);
  StringChangeEx(Result, #10, '', True);
  StringChangeEx(Result, #9, '', True);
end;

function JsonUnescape(const Value: string): string;
var
  i: Integer;
  Escaped: Boolean;
  Ch: Char;
begin
  Result := '';
  Escaped := False;
  for i := 1 to Length(Value) do
  begin
    Ch := Value[i];
    if Escaped then
    begin
      case Ch of
        '\': Result := Result + '\';
        '"': Result := Result + '"';
        '/': Result := Result + '/';
        'n': Result := Result + #13#10;
        'r': Result := Result + #13;
        't': Result := Result + #9;
      else
        Result := Result + Ch;
      end;
      Escaped := False;
    end
    else if Ch = '\' then
      Escaped := True
    else
      Result := Result + Ch;
  end;

  if Escaped then
    Result := Result + '\';
end;

function ExtractJsonStringValue(const Raw: string; const Key: string): string;
var
  Search: string;
  KeyPos: Integer;
  ColonPos: Integer;
  ValuePos: Integer;
  i: Integer;
  Escaped: Boolean;
  Buffer: string;
begin
  Result := '';
  Search := '"' + Key + '"';
  KeyPos := Pos(Search, Raw);
  if KeyPos <= 0 then
    Exit;

  ColonPos := KeyPos + Length(Search);
  while (ColonPos <= Length(Raw)) and (Raw[ColonPos] <> ':') do
    ColonPos := ColonPos + 1;
  if ColonPos > Length(Raw) then
    Exit;

  ValuePos := ColonPos + 1;
  while (ValuePos <= Length(Raw)) and ((Raw[ValuePos] = ' ') or (Raw[ValuePos] = #13) or (Raw[ValuePos] = #10) or (Raw[ValuePos] = #9)) do
    ValuePos := ValuePos + 1;
  if (ValuePos > Length(Raw)) or (Raw[ValuePos] <> '"') then
    Exit;

  Buffer := '';
  Escaped := False;
  ValuePos := ValuePos + 1;
  for i := ValuePos to Length(Raw) do
  begin
    if Escaped then
    begin
      Buffer := Buffer + '\' + Raw[i];
      Escaped := False;
    end
    else if Raw[i] = '\' then
      Escaped := True
    else if Raw[i] = '"' then
    begin
      Result := JsonUnescape(Buffer);
      Exit;
    end
    else
      Buffer := Buffer + Raw[i];
  end;
end;

function ExtractJsonBoolValue(const Raw: string; const Key: string; const DefaultValue: Boolean): Boolean;
var
  Search: string;
  KeyPos: Integer;
  ColonPos: Integer;
  ValuePos: Integer;
begin
  Result := DefaultValue;
  Search := '"' + Key + '"';
  KeyPos := Pos(Search, Raw);
  if KeyPos <= 0 then
    Exit;

  ColonPos := KeyPos + Length(Search);
  while (ColonPos <= Length(Raw)) and (Raw[ColonPos] <> ':') do
    ColonPos := ColonPos + 1;
  if ColonPos > Length(Raw) then
    Exit;

  ValuePos := ColonPos + 1;
  while (ValuePos <= Length(Raw)) and ((Raw[ValuePos] = ' ') or (Raw[ValuePos] = #13) or (Raw[ValuePos] = #10) or (Raw[ValuePos] = #9)) do
    ValuePos := ValuePos + 1;
  if ValuePos > Length(Raw) then
    Exit;

  if Lowercase(Copy(Raw, ValuePos, 4)) = 'true' then
    Result := True
  else if Lowercase(Copy(Raw, ValuePos, 5)) = 'false' then
    Result := False;
end;

procedure UpdateRCheckPage();
var
  Details: string;
begin
  if (RCheckStatusLabel = nil) or (RCheckDetailsLabel = nil) then
    Exit;

  if RCheckOk and RCheckCranReachable then
    RCheckStatusLabel.Caption := 'R encontrado e acesso ao CRAN confirmado.'
  else if not RCheckOk then
    RCheckStatusLabel.Caption := 'R nao encontrado ou versao incompativel.'
  else
    RCheckStatusLabel.Caption := 'R encontrado. O CRAN nao respondeu agora; a instalacao continuara com aviso.';

  Details := '';
  if DetectedRVersion <> '' then
    Details := Details + 'Versao detectada: ' + DetectedRVersion + #13#10;
  if RScriptPath <> '' then
    Details := Details + 'Rscript: ' + RScriptPath + #13#10;
  if RCheckSource <> '' then
    Details := Details + 'Origem: ' + RCheckSource + #13#10;
  if RCheckCranReachable then
    Details := Details + 'CRAN: acessivel' + #13#10
  else
    Details := Details + 'CRAN: indisponivel no momento' + #13#10;
  if RCheckMessage <> '' then
    Details := Details + #13#10 + RCheckMessage;

  RCheckDetailsLabel.Caption := Trim(Details);
  RCheckOpenSiteButton.Visible := not RCheckOk;
end;

function RunRPrereqCheck(): Boolean;
var
  ResultCode: Integer;
  Params: string;
  RawJson: AnsiString;
begin
  Result := False;
  RCheckOk := False;
  RCheckCranReachable := False;
  RScriptPath := '';
  DetectedRVersion := '';
  RCheckSource := '';
  RCheckMessage := '';
  if RCheckDownloadUrl = '' then
    RCheckDownloadUrl := 'https://cran.r-project.org/bin/windows/base/';

  if RCheckStatusLabel <> nil then
    RCheckStatusLabel.Caption := 'Verificando instalacao do R e acesso ao CRAN...';
  if RCheckDetailsLabel <> nil then
    RCheckDetailsLabel.Caption := 'Aguarde alguns segundos.';

  if FileExists(RCheckJsonPath) then
    DeleteFile(RCheckJsonPath);

  if not FileExists(RCheckScriptPath) then
  begin
    RCheckMessage := 'Script de verificacao do R nao encontrado no instalador.';
    UpdateRCheckPage();
    Exit;
  end;

  Params :=
    '-NoProfile -ExecutionPolicy Bypass -File "' + RCheckScriptPath + '" ' +
    '-JsonOut "' + RCheckJsonPath + '"';

  if not Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    RCheckMessage := 'Nao foi possivel executar a verificacao do R.';
    UpdateRCheckPage();
    Exit;
  end;

  if not FileExists(RCheckJsonPath) then
  begin
    RCheckMessage := 'A verificacao do R nao gerou o arquivo de diagnostico esperado.';
    UpdateRCheckPage();
    Exit;
  end;

  if not LoadStringFromFile(RCheckJsonPath, RawJson) then
  begin
    RCheckMessage := 'Nao foi possivel ler o diagnostico da verificacao do R.';
    UpdateRCheckPage();
    Exit;
  end;

  RCheckOk := ExtractJsonBoolValue(RawJson, 'ok', False);
  RCheckCranReachable := ExtractJsonBoolValue(RawJson, 'cran_reachable', False);
  RScriptPath := ExtractJsonStringValue(RawJson, 'rscript_path');
  DetectedRVersion := ExtractJsonStringValue(RawJson, 'version');
  RCheckSource := ExtractJsonStringValue(RawJson, 'source');
  RCheckMessage := ExtractJsonStringValue(RawJson, 'message_ptbr');
  RCheckDownloadUrl := ExtractJsonStringValue(RawJson, 'download_url');
  if RCheckDownloadUrl = '' then
    RCheckDownloadUrl := 'https://cran.r-project.org/bin/windows/base/';

  if RCheckOk and not RCheckCranReachable then
  begin
    if RCheckMessage <> '' then
      RCheckMessage := RCheckMessage + #13#10 + #13#10;
    RCheckMessage := RCheckMessage +
      'O R foi detectado, mas o instalador nao conseguiu acessar o CRAN.' + #13#10 +
      'A instalacao pode continuar; se pacotes R ficarem pendentes, use o reparo pelo Menu Iniciar.';
  end;

  UpdateRCheckPage();
  Result := RCheckOk;
end;

procedure OpenRDownloadSite(Sender: TObject);
var
  ResultCode: Integer;
begin
  if RCheckDownloadUrl = '' then
    RCheckDownloadUrl := 'https://cran.r-project.org/bin/windows/base/';
  ShellExec('open', RCheckDownloadUrl, '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
end;

procedure RetryRCheck(Sender: TObject);
begin
  RunRPrereqCheck();
end;

procedure InitializeWizard();
begin
  ExtractTemporaryFile('check_r.ps1');
  RCheckScriptPath := ExpandConstant('{tmp}\check_r.ps1');
  RCheckJsonPath := ExpandConstant('{tmp}\labiialex_r_check.json');
  RCheckDownloadUrl := 'https://cran.r-project.org/bin/windows/base/';

  RCheckPage := CreateCustomPage(
    wpWelcome,
    'Verificacao do R',
    'O labiia_lex usa automaticamente o R mais novo instalado e baixa pacotes do CRAN quando ha internet.'
  );

  RCheckIntroLabel := TNewStaticText.Create(RCheckPage);
  RCheckIntroLabel.Parent := RCheckPage.Surface;
  RCheckIntroLabel.Left := ScaleX(0);
  RCheckIntroLabel.Top := ScaleY(0);
  RCheckIntroLabel.Width := RCheckPage.SurfaceWidth;
  RCheckIntroLabel.AutoSize := False;
  RCheckIntroLabel.WordWrap := True;
  RCheckIntroLabel.Height := ScaleY(36);
  RCheckIntroLabel.Caption :=
    'Esta etapa verifica se ha um R compativel instalado. Se houver mais de um R, sera usado o mais novo.';

  RCheckStatusLabel := TNewStaticText.Create(RCheckPage);
  RCheckStatusLabel.Parent := RCheckPage.Surface;
  RCheckStatusLabel.Left := ScaleX(0);
  RCheckStatusLabel.Top := RCheckIntroLabel.Top + RCheckIntroLabel.Height + ScaleY(10);
  RCheckStatusLabel.Width := RCheckPage.SurfaceWidth;
  RCheckStatusLabel.AutoSize := False;
  RCheckStatusLabel.WordWrap := True;
  RCheckStatusLabel.Height := ScaleY(24);
  RCheckStatusLabel.Caption := 'A verificacao sera executada ao abrir esta pagina.';

  RCheckDetailsLabel := TNewStaticText.Create(RCheckPage);
  RCheckDetailsLabel.Parent := RCheckPage.Surface;
  RCheckDetailsLabel.Left := ScaleX(0);
  RCheckDetailsLabel.Top := RCheckStatusLabel.Top + RCheckStatusLabel.Height + ScaleY(8);
  RCheckDetailsLabel.Width := RCheckPage.SurfaceWidth;
  RCheckDetailsLabel.AutoSize := False;
  RCheckDetailsLabel.WordWrap := True;
  RCheckDetailsLabel.Height := ScaleY(130);
  RCheckDetailsLabel.Caption := '';

  RCheckRetryButton := TNewButton.Create(RCheckPage);
  RCheckRetryButton.Parent := RCheckPage.Surface;
  RCheckRetryButton.Left := ScaleX(0);
  RCheckRetryButton.Top := RCheckDetailsLabel.Top + RCheckDetailsLabel.Height + ScaleY(12);
  RCheckRetryButton.Width := ScaleX(130);
  RCheckRetryButton.Caption := 'Verificar novamente';
  RCheckRetryButton.OnClick := @RetryRCheck;

  RCheckOpenSiteButton := TNewButton.Create(RCheckPage);
  RCheckOpenSiteButton.Parent := RCheckPage.Surface;
  RCheckOpenSiteButton.Left := RCheckRetryButton.Left + RCheckRetryButton.Width + ScaleX(10);
  RCheckOpenSiteButton.Top := RCheckRetryButton.Top;
  RCheckOpenSiteButton.Width := ScaleX(150);
  RCheckOpenSiteButton.Caption := 'Abrir site do R';
  RCheckOpenSiteButton.OnClick := @OpenRDownloadSite;
  RCheckOpenSiteButton.Visible := False;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (RCheckPage <> nil) and (CurPageID = RCheckPage.ID) then
    RunRPrereqCheck();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (RCheckPage <> nil) and (CurPageID = RCheckPage.ID) then
  begin
    if not RunRPrereqCheck() then
    begin
      SuppressibleMsgBox(
        'O labiia_lex requer o R instalado neste computador.' + #13#10 + #13#10 +
        RCheckMessage,
        mbCriticalError,
        MB_OK,
        IDOK
      );
      Result := False;
    end
    else if not RCheckCranReachable then
    begin
      SuppressibleMsgBox(
        'O R foi encontrado, mas o instalador nao conseguiu acessar o CRAN agora.' + #13#10 + #13#10 +
        'A instalacao continuara. Se os pacotes R nao forem instalados, use o atalho "Reparar pacotes R do labiia_lex" depois.',
        mbInformation,
        MB_OK,
        IDOK
      );
    end;
  end;
end;

function RunPostInstallSelfTest(): Boolean;
var
  ResultCode: Integer;
  AppExe: string;
  Params: string;
  RunnerHash: string;
  RunnerPath: string;
  SelfTestRaw: AnsiString;
  SelfTestNormalized: string;
begin
  Result := False;
  LastProvisioningError := '';

  AppExe := ExpandConstant('{app}\LabiiaLex.exe');
  SelfTestJsonPath := AddBackslash(LogsRoot) + 'post_install_check.json';

  if not FileExists(AppExe) then
  begin
    SetProvisioningError('Executavel principal nao encontrado: ' + AppExe);
    Exit;
  end;

  RunnerPath := ResolveBundlePath('resources\gephi_runner\gephi-runner.jar');
  if not FileExists(RunnerPath) then
  begin
    SetProvisioningError('Gephi runner.jar ausente no pacote instalado.');
    Exit;
  end;

  if '{#GephiRunnerSHA256}' <> '' then
  begin
    RunnerHash := Lowercase(GetSHA256OfFile(RunnerPath));
    if RunnerHash <> Lowercase('{#GephiRunnerSHA256}') then
    begin
      SetProvisioningError('Integridade do gephi-runner.jar invalida (SHA256 divergente).');
      Exit;
    end;
  end;

  if FileExists(SelfTestJsonPath) then
    DeleteFile(SelfTestJsonPath);

  Params :=
    '/C set LEXIANALYST_SELF_TEST_PROFILE=installer_quick && "' + AppExe + '" --self-test --json-out "' + SelfTestJsonPath + '"';

  if not Exec(
    ExpandConstant('{cmd}'),
    Params,
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    Log('Falha ao executar autoteste do aplicativo.');
    SetProvisioningError('Falha ao executar autoteste do aplicativo.');
    Exit;
  end;

  if not FileExists(SelfTestJsonPath) then
  begin
    Log('Self-test JSON nao foi gerado: ' + SelfTestJsonPath);
    SetProvisioningError('Autoteste nao gerou resultado JSON: ' + SelfTestJsonPath);
    Exit;
  end;

  if not LoadStringFromFile(SelfTestJsonPath, SelfTestRaw) then
  begin
    Log('Nao foi possivel ler JSON do autoteste: ' + SelfTestJsonPath);
    SetProvisioningError('Nao foi possivel ler o resultado do autoteste: ' + SelfTestJsonPath);
    Exit;
  end;

  SelfTestNormalized := NormalizeForJsonSearch(SelfTestRaw);
  if Pos('"ok":true', SelfTestNormalized) <= 0 then
  begin
    Log('Validacao pos-instalacao indicou falha: ' + SelfTestRaw);
    SetProvisioningError(
      'Autoteste do aplicativo indicou falha. Verifique: ' + SelfTestJsonPath
    );
    Exit;
  end;

  if ResultCode <> 0 then
    Log('Self-test retornou ExitCode=' + IntToStr(ResultCode) + ', mas JSON ok=true.');

  Result := True;
end;


procedure CurStepChanged(CurStep: TSetupStep);
var
  ErrMsg: string;
begin
  if CurStep = ssPostInstall then
  begin
    PostInstallWarnings := '';
    try
      WizardForm.StatusLabel.Caption := 'Instalando pacotes R (pode demorar alguns minutos)...';
      WizardForm.StatusLabel.Update;

      if not RunRPackageProvisioning() then
        AddPostInstallWarning('Nao foi possivel instalar ou validar todos os pacotes R essenciais.');

      WizardForm.StatusLabel.Caption := 'Validando instalacao do labiia_lex...';
      WizardForm.StatusLabel.Update;

      if not RunPostInstallSelfTest() then
        AddPostInstallWarning('Autoteste rapido do labiia_lex indicou uma pendencia apos a instalacao.');
    except
      ErrMsg := GetExceptionMessage;
      SetProvisioningError('Erro interno no instalador: ' + ErrMsg);
      AddPostInstallWarning('Falha interna durante a configuracao automatica do labiia_lex.');
    end;
    ShowPostInstallWarnings();
  end;
end;


