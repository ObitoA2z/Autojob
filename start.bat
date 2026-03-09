@echo off
echo ===================================
echo    AutoJob - Candidature Automatique
echo ===================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe. Installez Python 3.10+
    pause
    exit /b 1
)

:: Create venv if needed
if not exist "venv" (
    echo [1/4] Creation de l'environnement virtuel...
    python -m venv venv
)

:: Activate venv
call venv\Scripts\activate.bat

:: Install dependencies
echo [2/4] Installation des dependances...
pip install -r requirements.txt -q

:: Install Playwright browsers
echo [3/4] Installation des navigateurs Playwright...
playwright install chromium

:: Start server
echo [4/4] Demarrage du serveur...
echo.
echo ===================================
echo   Ouvrez http://127.0.0.1:8000
echo ===================================
echo.
python main.py
pause
