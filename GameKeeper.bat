@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw -3 main.py & exit /b)
where pythonw >nul 2>nul && (start "" pythonw main.py & exit /b)
echo Python was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
pause
