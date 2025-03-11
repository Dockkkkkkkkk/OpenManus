Write-Host "===================================" -ForegroundColor Cyan
Write-Host "启动OpenManus AI助手" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan

# 初始化环境
Write-Host "正在初始化环境..." -ForegroundColor Yellow
python init_env.py

# 启动应用
Write-Host "正在启动应用..." -ForegroundColor Green
python main.py

# 如果程序意外退出，等待用户按键
if ($LASTEXITCODE -ne 0) {
    Write-Host "程序异常退出，错误代码: $LASTEXITCODE" -ForegroundColor Red
    Read-Host "按Enter键退出"
} 