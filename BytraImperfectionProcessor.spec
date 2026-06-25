# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Windows: .exe | macOS: .app"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

project_dir = Path(SPECPATH)
sys.path.insert(0, str(project_dir))

from branding import APP_BUILD_NAME, APP_NAME

app_bundle_name = f"{APP_NAME}.app"
build_name = APP_BUILD_NAME

# CI: PYINSTALLER_TARGET_ARCH=universal2 để chạy cả Intel + Apple Silicon
_mac_target_arch = os.environ.get("PYINSTALLER_TARGET_ARCH", "").strip() or None

datas = [(str(project_dir / "A_THANH"), "A_THANH")]

hiddenimports = [
    "abaqus_config",
    "abaqus_job_settings",
    "abaqus_postprocess",
    "batch_models",
    "abaqus_runner",
    "abaqus_writer",
    "app_runtime",
    "branding",
    "file_io",
    "incorporation",
    "inp_parser",
    "inp_writer",
    "inputs",
    "matlab_runner",
    "matlab_writer",
    "paths",
    "gui",
    "main",
]
hiddenimports += collect_submodules("openpyxl")

a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pandas", "numpy", "matplotlib", "scipy"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=build_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=_mac_target_arch,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=build_name,
)

# macOS: tao file .app de double-click (KHONG phai file .pkg trong thu muc build/)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=app_bundle_name,
        icon=None,
        bundle_identifier="com.bytra.imperfectionprocessor",
    )
