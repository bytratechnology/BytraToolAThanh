@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  Build Phan mem tu dong hoa (Windows)
echo ============================================

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Tao moi truong ao Python...
    python -m venv venv
    if errorlevel 1 (
        echo Loi: Can cai Python 3.10+ tu python.org
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

echo Cai dat thu vien...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo Dong goi bang PyInstaller...
pyinstaller BytraImperfectionProcessor.spec --noconfirm --clean
if errorlevel 1 exit /b 1

for /f "delims=" %%A in ('python -c "from branding import APP_BUILD_NAME; print(APP_BUILD_NAME)"') do set APP_NAME=%%A

echo Dang dong goi zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\%APP_NAME%' -DestinationPath 'dist\PhanMemTuDongHoa-Windows.zip' -Force"

echo.
echo ============================================
echo  HOAN TAT
echo  Thu muc cai dat: dist\%APP_NAME%\
echo  Chay file: dist\%APP_NAME%\%APP_NAME%.exe
echo  Gui nguoi dung: dist\PhanMemTuDongHoa-Windows.zip
echo.
echo  Tao file setup (tuy chon):
echo    Mo installer\setup.iss bang Inno Setup va bam Compile
echo ============================================

pause
