#!/usr/bin/env bash
# One-time setup: system tools (needs sudo), Python venv, npm packages.
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get install -y --no-install-recommends bubblewrap ghostscript pandoc tesseract-ocr \
  tesseract-ocr-eng libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-draw \
  fonts-dejavu-core libpango-1.0-0 libpangoft2-1.0-0 libmagic1 python3.12-venv unpaper
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend ci
npx --prefix frontend playwright install --with-deps chromium
