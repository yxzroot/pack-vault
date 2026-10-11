# Build with: python -m PyInstaller --noconfirm --clean pack-vault.spec
import sys

analysis = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=[("icon.svg", "."), ("chevron.svg", ".")],
    hiddenimports=["PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="PackVault",
    console=False,
    upx=False,
)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, name="PackVault", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(bundle, name="PackVault.app", icon=None,
                 bundle_identifier="io.github.yxzroot.packvault")
