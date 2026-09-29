@echo off
title Chatter Manager V2
echo.
echo  ========================================
echo  CHATTER MANAGER V2
echo  ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python introuvable. Installez Python depuis python.org
    pause & exit /b 1
)

echo Installation des dependances...
python -m pip install Flask Flask-Login python-dotenv reportlab --quiet --no-warn-script-location

if not exist .env (
    copy .env.example .env >nul 2>&1
    echo [INFO] Fichier .env cree depuis .env.example
    echo [INFO] Editez .env si necessaire puis relancez.
)

echo.
echo Demarrage sur http://127.0.0.1:5000
echo Ctrl+C pour arreter
echo.
python app.py
pause
