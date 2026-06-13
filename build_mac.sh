#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo " Build Phần mềm tự động hoá (macOS)"
echo "============================================"

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

pyinstaller BytraImperfectionProcessor.spec --noconfirm --clean

APP_NAME=$(python3 -c "from branding import APP_NAME; print(APP_NAME)")

echo "Dang dong goi zip..."
cd dist
rm -f PhanMemTuDongHoa-macOS.zip
zip -rq "PhanMemTuDongHoa-macOS.zip" "${APP_NAME}.app"
cd ..

echo ""
echo "============================================"
echo " HOAN TAT"
echo ""
echo "  MO UNG DUNG:"
echo "    dist/${APP_NAME}.app"
echo "    (double-click trong Finder)"
echo ""
echo "  GUI CHO NGUOI DUNG:"
echo "    dist/PhanMemTuDongHoa-macOS.zip"
echo ""
echo "  KHONG mo file trong thu muc build/"
echo "  (file .pkg o do KHONG phai bo cai)"
echo "============================================"
