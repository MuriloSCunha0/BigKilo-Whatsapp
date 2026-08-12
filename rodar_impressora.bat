@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Big Kilo - Impressora automatica

REM ================== CONFIG (edite se precisar) ==================
REM URL do sistema no Railway (o mesmo dominio do painel Big Kilo):
set PRINT_API_URL=https://web-production-467af.up.railway.app
REM Token: precisa ser IGUAL ao IMPRESSAO_API_TOKEN nas Variables do Railway:
set PRINT_API_TOKEN=VdzYOY7N0l_5wJ6E0kpM_-mVtV2EGgE4uZznbViygdY
REM Modo de impressao (windows = imprime na impressora instalada no Windows):
set PRINT_MODE=windows
REM Nome EXATO da impressora no Windows (rode "rodar_impressora.bat listar" p/ confirmar):
set PRINTER_NAME=ELGIN i9(USB)
REM Intervalo de verificacao de novos pedidos (segundos):
set PRINT_POLL_SECONDS=5
REM ===============================================================

REM Garante a dependencia do modo windows (so na 1a vez demora):
python -m pip install --quiet pywin32 2>nul

if /I "%1"=="listar" ( python print_agent.py --listar & echo. & pause & exit /b )
if /I "%1"=="teste"  ( python print_agent.py --teste  & echo. & pause & exit /b )

echo ============================================================
echo   Big Kilo - Impressao automatica de comandas
echo   Impressora: %PRINTER_NAME%
echo   Servidor:   %PRINT_API_URL%
echo   (Deixe esta janela ABERTA. Feche para parar de imprimir.)
echo ============================================================
python print_agent.py
echo.
echo O agente parou. Pressione uma tecla para fechar.
pause >nul
