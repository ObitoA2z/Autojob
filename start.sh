#!/bin/bash
echo "==================================="
echo "   AutoJob - Candidature Automatique"
echo "==================================="
echo ""

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "[1/4] Creation de l'environnement virtuel..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "[2/4] Installation des dependances..."
pip install -r requirements.txt -q

# Install Playwright browsers
echo "[3/4] Installation des navigateurs Playwright..."
playwright install chromium

# Start server
echo "[4/4] Demarrage du serveur..."
echo ""
echo "==================================="
echo "  Ouvrez http://127.0.0.1:8000"
echo "==================================="
echo ""
python main.py
