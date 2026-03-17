# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置 - 网文清洗器
# 运行: pyinstaller cleaner.spec

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# 收集 Gradio 及其依赖所需的数据文件
# 注意：safehttpx、groovy 等包在启动时读取 version.txt，必须打包进 exe
def _collect_pkg_data(pkg_name):
    try:
        return collect_data_files(pkg_name, include_py_files=False)
    except Exception:
        return []

# 必须包含 version.txt 的包（Gradio 依赖，启动时读取）
_version_pkgs = ['safehttpx', 'groovy']
# Gradio 主包及客户端
_gradio_pkgs = ['gradio', 'gradio_client']

_all_datas = []
for pkg in _version_pkgs + _gradio_pkgs:
    _all_datas.extend(_collect_pkg_data(pkg))

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('prompts', 'prompts'),  # 打包提示词文件夹
    ] + _all_datas,
    hiddenimports=[
        'gradio',
        'gradio_client',
        'safehttpx',
        'groovy',
        'charset_normalizer',
        'openai',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    # Gradio 在运行时用 inspect.getfile() + read_text() 读取 .py 源文件，
    # 必须将 gradio 以 .py 形式打包，否则会报 FileNotFoundError
    module_collection_mode={
        'gradio': 'py',
    },
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NovelCleaner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 关闭 UPX 可大幅加快打包速度，避免长时间无输出
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示黑色控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
