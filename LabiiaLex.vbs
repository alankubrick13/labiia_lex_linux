' LabiiaLex.vbs — Launcher VBScript sem janela de console.
'
' Use este arquivo para criar atalhos na área de trabalho.
' Clique duplo executa o LabiiaLex sem abrir janela de CMD.
'
' Como criar um atalho:
'   1. Clique com o botão direito neste arquivo → Criar atalho
'   2. Mova o atalho para onde quiser (ex: Área de trabalho)

Dim oShell, oFSO, sDir, sPyw

Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

' Pasta onde este .vbs está (=pasta do projeto)
sDir = oFSO.GetParentFolderName(WScript.ScriptFullName)

' Prefere LabiiaLex.pyw (pythonw, sem console)
sPyw = sDir & "\LabiiaLex.pyw"

If oFSO.FileExists(sPyw) Then
    ' wscript executa .pyw via pythonw.exe automaticamente → sem console
    oShell.Run "wscript //B """ & sPyw & """", 0, False
Else
    ' Fallback: main.py via pythonw.exe direto
    Dim sPython, sMain
    sPython = oShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & _
              "\Programs\Python\Python313\pythonw.exe"
    sMain   = sDir & "\main.py"
    If Not oFSO.FileExists(sPython) Then
        sPython = "pythonw.exe"
    End If
    oShell.Run """" & sPython & """ """ & sMain & """", 0, False
End If

Set oFSO   = Nothing
Set oShell = Nothing
