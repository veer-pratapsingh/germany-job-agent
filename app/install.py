"""Installs the app's one dependency and puts a "Germany Job Agent" shortcut on the desktop and in the Start menu.

usage: python app/install.py
"""
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent


def q(p) -> str:
    """A PowerShell single-quoted string."""
    return "'" + str(p).replace("'", "''") + "'"


subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(APP / "requirements.txt")], check=True)
pythonw = Path(sys.executable).with_name("pythonw.exe")
script = f"""
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {{
  $link = $shell.CreateShortcut((Join-Path $dir 'Germany Job Agent.lnk'))
  $link.TargetPath = {q(pythonw if pythonw.exists() else sys.executable)}
  $link.Arguments = {q(f'"{APP / "job_agent.py"}"')}
  $link.WorkingDirectory = {q(APP.parent)}
  $link.IconLocation = {q(APP / "icon.ico")}
  $link.Description = 'Find new jobs in Germany and build CVs and cover letters with Claude Code or Codex'
  $link.Save()
  Write-Output "Created $($link.FullName)"
}}
"""
subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
