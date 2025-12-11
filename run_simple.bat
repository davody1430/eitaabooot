@echo off
chcp 65001
cls
echo ========================================
echo 🤖 ربات ایتا - نسخه ساده
echo ========================================
echo.

REM بررسی پایتون
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ پایتون یافت نشد!
    pause
    exit /b 1
)

echo 📦 بررسی پکیج‌ها...
python -c "import flask" 2>nul
if errorlevel 1 (
    echo ⚠️ Flask نصب نیست. در حال نصب...
    pip install flask flask-cors
)

echo.
echo 🚀 در حال راه‌اندازی سرور...
echo 🌐 بعد از اجرا، به آدرس زیر بروید:
echo    http://localhost:5000
echo.
echo ⚠️  این پنجره را نبندید!
echo.

python backend\app.py

pause