#define MyAppName "AI Drawing Copilot"
#define MyAppVersion "0.2.0"
#define MyAppExeName "AIDrawingCopilot.exe"
#ifndef AppSourceDir
  #define AppSourceDir "..\dist\AIDrawingCopilot"
#endif

[Setup]
AppId={{7A5C80C7-D548-4BEF-A136-E71A54BE9212}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={localappdata}\Programs\AIDrawingCopilot
DefaultGroupName={#MyAppName}
DisableWelcomePage=no
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=no
DisableStartupPrompt=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AIDrawingCopilot-Setup-{#MyAppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName=Uninstall {#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
AllowCancelDuringInstall=no
CloseApplications=no
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
; A single compiler language prevents Inno Setup's separate language popup.
; The first integrated wizard page below handles Chinese/English selection.
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Base application files: never import the developer's portable marker/data.
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Excludes: "portable.mode,data,data\*"; Flags: ignoreversion recursesubdirs
; Portable mode installs only the marker. Runtime-created data is not entered
; into the uninstall database and therefore is not deleted by unins000.exe.
Source: "{#AppSourceDir}\portable.mode"; DestDir: "{app}"; Check: IsPortableMode; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\AI Drawing Copilot"; Filename: "{app}\{#MyAppExeName}"; Check: ShouldCreateStartMenuShortcut
Name: "{autodesktop}\AI Drawing Copilot"; Filename: "{app}\{#MyAppExeName}"; Check: ShouldCreateDesktopShortcut

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{code:GetLaunchDescription}"; Flags: nowait postinstall skipifsilent

; Intentionally no [UninstallDelete] wildcard rules.
; unins000.exe removes only installer-registered binaries, marker files and
; shortcuts. AppData, portable runtime data and unrelated files are excluded.

[Code]
var
  IsChinese: Boolean;
  LanguageSelected: Boolean;
  ChineseButton: TPanel;
  EnglishButton: TPanel;
  InfoPage: TWizardPage;
  InfoTitle: TNewStaticText;
  InfoBody: TNewStaticText;
  ModePage: TInputOptionWizardPage;
  ShortcutPage: TInputOptionWizardPage;

function IsPortableMode: Boolean;
begin
  Result := (ModePage <> nil) and (ModePage.SelectedValueIndex = 1);
end;

function ShouldCreateStartMenuShortcut: Boolean;
begin
  Result := (ShortcutPage <> nil) and ShortcutPage.Values[0];
end;

function ShouldCreateDesktopShortcut: Boolean;
begin
  Result := (ShortcutPage <> nil) and ShortcutPage.Values[1];
end;

function GetLaunchDescription(Param: String): String;
begin
  if IsChinese then
    Result := '启动 AI Drawing Copilot'
  else
    Result := 'Launch AI Drawing Copilot';
end;

procedure SetPageHeader(const AName, ADescription: String);
begin
  WizardForm.PageNameLabel.Caption := AName;
  WizardForm.PageDescriptionLabel.Caption := ADescription;
end;

procedure ApplyBuiltInPageLanguage;
begin
  if IsChinese then
  begin
    WizardForm.SelectDirLabel.Caption :=
      'AI Drawing Copilot 将安装到以下文件夹。';
    WizardForm.SelectDirBrowseLabel.Caption :=
      '如需更换文件夹，请点击“浏览”；确认后点击“下一步”。';
    WizardForm.DirBrowseButton.Caption := '浏览...';
    WizardForm.DiskSpaceLabel.Caption := '请确保目标磁盘具有足够的可用空间。';
    WizardForm.ReadyLabel.Caption := '请确认以下设置，然后点击“安装”。';
    WizardForm.FinishedHeadingLabel.Caption := '安装完成';
    WizardForm.FinishedLabel.Caption :=
      'AI Drawing Copilot 已安装完成。点击“完成”退出安装向导。';
  end
  else
  begin
    WizardForm.SelectDirLabel.Caption :=
      'Setup will install AI Drawing Copilot into the following folder.';
    WizardForm.SelectDirBrowseLabel.Caption :=
      'To choose a different folder, click Browse. When ready, click Next.';
    WizardForm.DirBrowseButton.Caption := 'Browse...';
    WizardForm.DiskSpaceLabel.Caption :=
      'Make sure the destination drive has enough free disk space.';
    WizardForm.ReadyLabel.Caption := 'Review the settings below, then click Install.';
    WizardForm.FinishedHeadingLabel.Caption := 'Installation complete';
    WizardForm.FinishedLabel.Caption :=
      'AI Drawing Copilot has been installed. Click Finish to close Setup.';
  end;
end;

procedure ApplyLanguage;
begin
  WizardForm.Caption := 'AI Drawing Copilot 0.2.0';
  if IsChinese then
  begin
    WizardForm.WelcomeLabel1.Caption := '选择安装器语言';
    WizardForm.WelcomeLabel2.Caption :=
      '请选择本安装向导使用的语言。语言选择、软件说明、安装模式、路径、快捷方式和摘要都在这个主窗口中完成。';
    WizardForm.NextButton.Caption := '下一步 >';
    WizardForm.BackButton.Caption := '< 上一步';
    WizardForm.CancelButton.Caption := '取消';
    ChineseButton.Caption := '●  中文';
    EnglishButton.Caption := 'English';
    ChineseButton.Color := StrToColor('#DCEBFF');
    EnglishButton.Color := clWindow;
    InfoPage.Caption := '关于本程序';
    InfoPage.Description := '用途与数据位置';
    InfoTitle.Caption := 'AI Drawing Copilot 0.2.0';
    InfoBody.Caption :=
      '这是一个本地 AI 作图构图工具，用于组织区域、层级、自然语言关系，并导出给不同能力的生图模型。' + #13#10 + #13#10 +
      '程序本身不联网。普通模式把设置保存在当前用户目录；便携模式把设置保存在安装目录旁。';
    ModePage.Caption := '安装模式';
    ModePage.Description := '';
    ModePage.SubCaptionLabel.Caption := '';
    ModePage.CheckListBox.ItemCaption[0] := '普通模式（推荐）';
    ModePage.CheckListBox.ItemCaption[1] := '便携模式';
    ShortcutPage.Caption := '选择快捷方式';
    ShortcutPage.Description := '选择需要创建的入口';
    ShortcutPage.SubCaptionLabel.Caption := '这些快捷方式也会由 EXE 卸载器安全移除。';
    ShortcutPage.CheckListBox.ItemCaption[0] := '创建开始菜单快捷方式';
    ShortcutPage.CheckListBox.ItemCaption[1] := '创建桌面快捷方式';
  end
  else
  begin
    WizardForm.WelcomeLabel1.Caption := 'Choose installer language';
    WizardForm.WelcomeLabel2.Caption :=
      'Choose the language used by this installer. Language, information, mode, destination, shortcuts, and summary all stay inside this wizard window.';
    WizardForm.NextButton.Caption := 'Next >';
    WizardForm.BackButton.Caption := '< Back';
    WizardForm.CancelButton.Caption := 'Cancel';
    ChineseButton.Caption := '中文';
    EnglishButton.Caption := '●  English';
    ChineseButton.Color := clWindow;
    EnglishButton.Color := StrToColor('#DCEBFF');
    InfoPage.Caption := 'About this application';
    InfoPage.Description := 'Purpose and data location';
    InfoTitle.Caption := 'AI Drawing Copilot 0.2.0';
    InfoBody.Caption :=
      'A local composition tool for organizing regions, layers, natural-language relationships, and exports for image models with different capabilities.' + #13#10 + #13#10 +
      'The application does not connect to the internet. Standard mode stores settings in the current user profile; portable mode stores them beside the application.';
    ModePage.Caption := 'Install mode';
    ModePage.Description := '';
    ModePage.SubCaptionLabel.Caption := '';
    ModePage.CheckListBox.ItemCaption[0] := 'Standard mode (recommended)';
    ModePage.CheckListBox.ItemCaption[1] := 'Portable mode';
    ShortcutPage.Caption := 'Choose shortcuts';
    ShortcutPage.Description := 'Select the application entry points to create';
    ShortcutPage.SubCaptionLabel.Caption := 'These shortcuts are also safely removed by the EXE uninstaller.';
    ShortcutPage.CheckListBox.ItemCaption[0] := 'Create Start menu shortcut';
    ShortcutPage.CheckListBox.ItemCaption[1] := 'Create desktop shortcut';
  end;
  ApplyBuiltInPageLanguage;
end;

procedure LanguageClick(Sender: TObject);
begin
  IsChinese := Sender = ChineseButton;
  LanguageSelected := True;
  ApplyLanguage;
  WizardForm.NextButton.Enabled := True;
end;

procedure InitializeWizard;
var
  LanguageButtonWidth: Integer;
begin
  LanguageSelected := WizardSilent;
  IsChinese := False;

  WizardForm.WelcomeLabel1.Caption := '选择语言 / Choose Language';
  WizardForm.WelcomeLabel2.Caption :=
    '请选择安装器语言，然后继续。' + #13#10 + 'Choose the installer language, then continue.';

  LanguageButtonWidth := (WizardForm.WelcomeLabel2.Width - ScaleX(18)) div 2;

  ChineseButton := TPanel.Create(WizardForm.WelcomePage);
  ChineseButton.Parent := WizardForm.WelcomePage;
  ChineseButton.Caption := '中文';
  ChineseButton.Left := WizardForm.WelcomeLabel2.Left;
  ChineseButton.Top := WizardForm.WelcomeLabel2.Top + ScaleY(112);
  ChineseButton.Width := LanguageButtonWidth;
  ChineseButton.Height := ScaleY(68);
  ChineseButton.Color := clWindow;
  ChineseButton.BevelKind := bkFlat;
  ChineseButton.BevelOuter := bvNone;
  ChineseButton.ParentBackground := False;
  ChineseButton.Font.Size := 15;
  ChineseButton.Font.Style := [fsBold];
  ChineseButton.OnClick := @LanguageClick;

  EnglishButton := TPanel.Create(WizardForm.WelcomePage);
  EnglishButton.Parent := WizardForm.WelcomePage;
  EnglishButton.Caption := 'English';
  EnglishButton.Left := ChineseButton.Left + LanguageButtonWidth + ScaleX(18);
  EnglishButton.Top := ChineseButton.Top;
  EnglishButton.Width := LanguageButtonWidth;
  EnglishButton.Height := ChineseButton.Height;
  EnglishButton.Color := clWindow;
  EnglishButton.BevelKind := bkFlat;
  EnglishButton.BevelOuter := bvNone;
  EnglishButton.ParentBackground := False;
  EnglishButton.Font.Size := 15;
  EnglishButton.Font.Style := [fsBold];
  EnglishButton.OnClick := @LanguageClick;

  InfoPage := CreateCustomPage(wpWelcome, 'About this application', 'Purpose, privacy, and uninstall scope');
  InfoTitle := TNewStaticText.Create(InfoPage);
  InfoTitle.Parent := InfoPage.Surface;
  InfoTitle.Left := 0;
  InfoTitle.Top := ScaleY(8);
  InfoTitle.Width := InfoPage.SurfaceWidth;
  InfoTitle.Font.Style := [fsBold];
  InfoTitle.Font.Size := 13;

  InfoBody := TNewStaticText.Create(InfoPage);
  InfoBody.Parent := InfoPage.Surface;
  InfoBody.Left := 0;
  InfoBody.Top := ScaleY(48);
  InfoBody.Width := InfoPage.SurfaceWidth;
  InfoBody.Height := ScaleY(125);
  InfoBody.AutoSize := False;
  InfoBody.WordWrap := True;

  ModePage := CreateInputOptionPage(InfoPage.ID, 'Install mode', '', '', True, False);
  ModePage.Add('Standard mode');
  ModePage.Add('Portable mode');
  ModePage.SelectedValueIndex := 0;
  ModePage.CheckListBox.Font.Size := 15;
  ModePage.CheckListBox.MinItemHeight := ScaleY(42);
  ModePage.CheckListBox.Height := ScaleY(112);
  ModePage.CheckListBox.Offset := ScaleX(8);

  ShortcutPage := CreateInputOptionPage(wpSelectDir, 'Choose shortcuts', 'Select application entry points', 'Choose any shortcuts:', False, False);
  ShortcutPage.Add('Create Start menu shortcut');
  ShortcutPage.Add('Create desktop shortcut');
  ShortcutPage.Values[0] := True;
  ShortcutPage.Values[1] := False;
  ShortcutPage.CheckListBox.Font.Size := 14;
  ShortcutPage.CheckListBox.MinItemHeight := ScaleY(40);
  ShortcutPage.CheckListBox.Height := ScaleY(108);
  ShortcutPage.CheckListBox.Offset := ScaleX(8);

  if CompareText(ExpandConstant('{param:PORTABLE|0}'), '1') = 0 then
    ModePage.SelectedValueIndex := 1;

  if WizardSilent then
    ApplyLanguage;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  { Exit immediately. Do not open Inno Setup's separately localized
    confirmation dialog over the integrated wizard. }
  Confirm := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpWelcome then
  begin
    Result := LanguageSelected;
    if not Result then
      WizardForm.NextButton.Enabled := False;
  end;
  if CurPageID = ModePage.ID then
  begin
    { Only replace one of our own defaults. Preserve a path supplied through
      /DIR or typed by the user before returning to this page. }
    if (CompareText(WizardForm.DirEdit.Text,
         ExpandConstant('{localappdata}\Programs\AIDrawingCopilot')) = 0) or
       (CompareText(WizardForm.DirEdit.Text,
         ExpandConstant('{userdesktop}\AIDrawingCopilot-Portable')) = 0) then
    begin
      if IsPortableMode then
        WizardForm.DirEdit.Text := ExpandConstant('{userdesktop}\AIDrawingCopilot-Portable')
      else
        WizardForm.DirEdit.Text := ExpandConstant('{localappdata}\Programs\AIDrawingCopilot');
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
  begin
    WizardForm.NextButton.Enabled := LanguageSelected;
    Exit;
  end;

  ApplyBuiltInPageLanguage;

  if IsChinese then
  begin
    WizardForm.NextButton.Caption := '下一步 >';
    WizardForm.BackButton.Caption := '< 上一步';
    WizardForm.CancelButton.Caption := '取消';
    if CurPageID = InfoPage.ID then
      SetPageHeader('关于本程序', '用途与数据位置')
    else if CurPageID = ModePage.ID then
      SetPageHeader('安装模式', '')
    else if CurPageID = wpSelectDir then
      SetPageHeader('选择安装位置', '选择程序文件所在目录')
    else if CurPageID = ShortcutPage.ID then
      SetPageHeader('选择快捷方式', '选择需要创建的程序入口')
    else if CurPageID = wpReady then
    begin
      SetPageHeader('准备安装', '确认以下设置，然后开始安装');
      WizardForm.NextButton.Caption := '安装';
    end
    else if CurPageID = wpInstalling then
      SetPageHeader('正在安装', '请稍候，程序文件正在写入')
    else if CurPageID = wpFinished then
    begin
      SetPageHeader('安装完成', 'AI Drawing Copilot 已经可以使用');
      WizardForm.NextButton.Caption := '完成';
    end;
  end
  else
  begin
    WizardForm.NextButton.Caption := 'Next >';
    WizardForm.BackButton.Caption := '< Back';
    WizardForm.CancelButton.Caption := 'Cancel';
    if CurPageID = InfoPage.ID then
      SetPageHeader('About this application', 'Purpose and data location')
    else if CurPageID = ModePage.ID then
      SetPageHeader('Install mode', '')
    else if CurPageID = wpSelectDir then
      SetPageHeader('Choose destination', 'Select the folder for program files')
    else if CurPageID = ShortcutPage.ID then
      SetPageHeader('Choose shortcuts', 'Select application entry points')
    else if CurPageID = wpReady then
    begin
      SetPageHeader('Ready to install', 'Review the settings and begin installation');
      WizardForm.NextButton.Caption := 'Install';
    end
    else if CurPageID = wpInstalling then
      SetPageHeader('Installing', 'Please wait while program files are written')
    else if CurPageID = wpFinished then
    begin
      SetPageHeader('Installation complete', 'AI Drawing Copilot is ready to use');
      WizardForm.NextButton.Caption := 'Finish';
    end;
  end;
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
begin
  if IsChinese then
    WizardForm.StatusLabel.Caption := '正在写入程序文件...'
  else
    WizardForm.StatusLabel.Caption := 'Writing program files...';
end;

function UpdateReadyMemo(
  Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String
): String;
var
  ModeText, ShortcutText: String;
begin
  if IsChinese then
  begin
    if IsPortableMode then ModeText := '便携模式' else ModeText := '普通模式';
    ShortcutText := '';
    if ShouldCreateStartMenuShortcut then ShortcutText := ShortcutText + NewLine + Space + '开始菜单';
    if ShouldCreateDesktopShortcut then ShortcutText := ShortcutText + NewLine + Space + '桌面';
    if ShortcutText = '' then ShortcutText := NewLine + Space + '不创建快捷方式';
    Result :=
      '安装模式：' + NewLine + Space + ModeText + NewLine + NewLine +
      '安装位置：' + NewLine + Space + WizardDirValue + NewLine + NewLine +
      '快捷方式：' + ShortcutText + NewLine + NewLine +
      '卸载器：' + NewLine + Space + '安装目录中的 unins000.exe（仅删除登记文件）';
  end
  else
  begin
    if IsPortableMode then ModeText := 'Portable mode' else ModeText := 'Standard mode';
    ShortcutText := '';
    if ShouldCreateStartMenuShortcut then ShortcutText := ShortcutText + NewLine + Space + 'Start menu';
    if ShouldCreateDesktopShortcut then ShortcutText := ShortcutText + NewLine + Space + 'Desktop';
    if ShortcutText = '' then ShortcutText := NewLine + Space + 'No shortcuts';
    Result :=
      'Installation mode:' + NewLine + Space + ModeText + NewLine + NewLine +
      'Destination:' + NewLine + Space + WizardDirValue + NewLine + NewLine +
      'Shortcuts:' + ShortcutText + NewLine + NewLine +
      'Uninstaller:' + NewLine + Space + 'unins000.exe in the install folder (registered files only)';
  end;
end;
