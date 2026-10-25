"""Launch the delivered EXE and verify ready/singleton logs; no UI input."""
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT.parent/'交付包/森林小博士—电脑本地版'
sys.path.insert(0,str(PACKAGE/'desktop'))
from single_instance import SingleInstance

guard=SingleInstance()
try:
    free=guard.acquire()
finally:
    guard.close()
if not free:
    raise SystemExit('Existing classroom app is running; preserve it, restart with latest package to validate.')
log=PACKAGE/'data/classroom.log'
previous=log.stat().st_size if log.exists() else 0
exe=PACKAGE/'启动森林小博士—电脑本地版.exe'
def launch():
    p=subprocess.Popen([str(exe)],cwd=str(PACKAGE),creationflags=0x08000000)
    assert p.wait(timeout=10)==0
def latest():
    if not log.exists():return ''
    with log.open('rb') as f:
        f.seek(previous)
        return f.read().decode('utf-8',errors='replace')
launch()
for _ in range(100):
    text=latest()
    if '[就绪] 悬浮窗已显示' in text:break
    if 'Traceback' in text:raise RuntimeError('Launcher failed; see data/classroom.log')
    time.sleep(.3)
else:raise RuntimeError('No native floating-window readiness after 30s')
for _ in range(3):launch()
for _ in range(30):
    text=latest()
    if text.count('[复用] 森林小博士已在运行')>=3:break
    time.sleep(.2)
assert text.count('[就绪] 悬浮窗已显示')==1
assert text.count('[复用] 森林小博士已在运行')>=3
for _ in range(50):
    text=latest()
    if '[就绪] 聊天面板已显示：2个教学入口' in text:break
    if '[错误] 无法创建教师对话框' in text:raise RuntimeError('Native chat initialization failed; see classroom.log')
    time.sleep(.2)
else:raise RuntimeError('Native chat window did not become ready after duplicate launch')
print('PASS delivered EXE -> bundled runtime -> native floating window')
print('PASS repeated EXE launch: one native instance, existing window activated')
print('PASS actual native chat window initialized with two teaching entries')
print('Classroom app remains running for user preview')
