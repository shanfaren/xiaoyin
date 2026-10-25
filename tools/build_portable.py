"""Build a private, self-contained Windows classroom distribution."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / '交付包'
PACKAGE = OUT / '森林小博士_本地电脑版'


def build():
    if PACKAGE.exists():
        raise RuntimeError('Output already exists; preserve prior delivery and use another name.')
    PACKAGE.mkdir(parents=True)
    for folder in ('backend', 'desktop', 'web', 'assets'):
        shutil.copytree(ROOT / folder, PACKAGE / folder,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.md'))
    (PACKAGE / 'config').mkdir()
    cfg = json.loads((ROOT / 'config/config.json').read_text(encoding='utf-8'))
    cfg['server'].update(host='127.0.0.1', port=18080, public_base_url='',
                         trust_proxy_headers=False)
    (PACKAGE / 'config/config.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
    runtime = PACKAGE / 'runtime'
    runtime.mkdir()
    archive = ROOT / 'build-cache/python-3.12.10-embed-amd64.zip'
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError('Invalid runtime archive: ' + bad)
        z.extractall(runtime)
    (runtime / 'python312._pth').write_text('python312.zip\n.\n..\n..\\desktop\n', encoding='utf-8')
    (PACKAGE / 'data').mkdir()
    (PACKAGE / 'start.py').write_text('''from pathlib import Path
import os, sys, traceback
root = Path(__file__).resolve().parent
os.chdir(root)
(root / 'data').mkdir(exist_ok=True)
log = open(root / 'data' / 'classroom.log', 'a', encoding='utf-8', buffering=1)
sys.stdout = sys.stderr = log
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'desktop'))
sys.argv = [str(root / 'desktop' / 'launcher.py'), '--port', '18080']
try:
    from desktop.launcher import main
    main()
except Exception:
    traceback.print_exc()
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, '启动失败，请查看 data/classroom.log。', '森林小博士', 16)
''', encoding='utf-8')
    vbs = '''Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
shell.Run Chr(34) & folder & "\\runtime\\pythonw.exe" & Chr(34) & " " & Chr(34) & folder & "\\start.py" & Chr(34), 0, False
'''
    (PACKAGE / '双击启动.vbs').write_text(vbs, encoding='utf-16')
    (PACKAGE / '备用启动.cmd').write_bytes(('@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0runtime\\pythonw.exe" "%~dp0start.py"\r\n').encode('gbk'))
    (PACKAGE / '使用说明.txt').write_text('''森林小博士 · 本地电脑课堂版

适用：Windows 10/11 64 位电脑。无需安装 Python，无需安装浏览器插件。
先将压缩包全部解压到桌面或文档目录，再双击“启动森林小博士.exe”。
也可双击“双击启动.vbs”或“备用启动.cmd”。不能直接在压缩包里运行。

打开希沃课件后启动本程序，桌面出现可拖动悬浮球。
点击悬浮球展开对话，点击减号收起；置顶按钮控制课堂展示。
三个入口：提问答疑、探究提示、收获分享。
可以打字或点击语音按钮录音，停止录音后会识别并发送，回复自动朗读。
右击悬浮球，选择“退出森林小博士”可结束程序与本程序启动的服务。
运行后会在 data 目录保存当前电脑的会话与日志；本交付包不带历史对话。

需要联网调用豆包、语音识别和语音合成；“本地版”指本地桌面程序，不是离线大模型。
已有 API 配置已随包带入，不用重新填写。此包含你的私密 API 配置，请仅复制到可信的课堂电脑，不要上传公开网盘或代码仓库。
首次使用语音时，请确保麦克风、扬声器可用，并在 Windows 设置中允许桌面应用访问麦克风。
本机服务仅监听本机回环地址，不对课堂局域网开放。
若无声音，请检查系统音量及输出设备。若启动失败，查看 data/classroom.log。

本地电脑版和手机扫码版独立运行，各终端各自对话。
''', encoding='utf-8-sig')
    # Copy the interpreter as a named executable and pair it with the app entry.
    # pythonw executes __main__.py from an adjacent directory named after it
    # only with an explicit argument, so a native launcher is built separately.
    manifest = {'name': '森林小博士', 'runtime': 'CPython 3.12.10 Windows x64 embedded',
                'runtime_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'private_config_included': True, 'history_included': False}
    (PACKAGE / 'package-info.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(PACKAGE))


if __name__ == '__main__':
    build()
