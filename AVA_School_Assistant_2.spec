# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('config.default.json', '.')]
binaries = []
hiddenimports = [
    'core.written_solver',
    'core.spellcheck',
    'core.humanizer',
    'core.humanizer.client',
    'core.humanizer.models',
    'core.humanizer.engine',
    'core.humanizer.engine.deep',
    'core.humanizer.engine.generator',
    'core.humanizer.engine.guardrails',
    'core.humanizer.engine.prompt',
    'core.humanizer.engine.readability',
    'core.humanizer.engine.thesaurus',
    'core.humanizer.parser',
    'core.playground',
    'core.playground.project_model',
    'core.playground.doc_io',
    'core.playground.humanizer_bridge',
    'core.playground.engine',
    'core.playground.teacher_evaluator',
    'core.playground.web_source',
    'ui.playground',
    'ui.playground.workspace',
    'ui.playground.rubric_viewer',
    'ui.home_view',
    'humanizer',
    'docx',
    'pypdf',
]
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret2 = collect_all('docx')
datas += tmp_ret2[0]; binaries += tmp_ret2[1]; hiddenimports += tmp_ret2[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AVA_School_Assistant_2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
