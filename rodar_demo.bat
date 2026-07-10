@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   Big Kilo - subindo demo (servidor + ngrok)
echo ================================================
echo.

REM 1) Servidor Django (janela propria)
start "Big Kilo - Servidor" cmd /k "python manage.py runserver 0.0.0.0:8000"

REM 2) Espera o servidor subir
timeout /t 4 >nul

REM 3) Tunel ngrok (janela propria - a URL aparece aqui)
start "Big Kilo - ngrok" cmd /k "ngrok http 8000"

echo.
echo Pronto! A URL publica aparece na janela "Big Kilo - ngrok"
echo (linha Forwarding  https://....ngrok-free.app)
echo Mande essa URL + /admin/ para o cliente.  Login: admin / admin123
echo.
echo Para encerrar a demo, feche as duas janelas que abriram.
pause
