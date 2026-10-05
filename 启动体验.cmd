@echo off
chcp 65001 >nul
echo 正在启动本地模型，请稍候；就绪后会自动打开体验页面。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0v5\open_demo.ps1"
if errorlevel 1 (
  echo 启动失败，请查看上面的提示或联系项目开发者。
  pause
)
