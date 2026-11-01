@echo off
title Dual-Engine Macro: US Stocks vs Counter-DXY -> Gold Forecast
cd /d "%~dp0.."

echo ============================================================================
echo   DUAL-ENGINE MACRO: US EQUITIES vs COUNTER-DXY -^> GOLD (XAU/USD) FORECAST
echo ============================================================================
echo.
echo  [1] Buka Dashboard GUI (Disertai Tombol Cek Manual Keaslian Data)
echo  [2] Jalankan di Terminal CLI Langsung
echo  [3] Keluar
echo.
set /p opt="Pilihan Anda (1/2/3) [Default: 1]: "
if "%opt%"=="2" goto :cli
if "%opt%"=="3" exit /b 0

:gui
start "" python trader-macro\gui.py
exit /b 0

:cli
cls
python trader-macro\forecast.py --write
echo.
pause
exit /b 0
