"""Ship the single-instance fix to the existing private classroom package."""
from pathlib import Path
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / '交付包'
package = OUT / '森林小博士_本地电脑版'
assert package.is_dir()
for name in ('single_instance.py', 'launcher.py', 'floating.py'):
    shutil.copy2(ROOT / 'desktop' / name, package / 'desktop' / name)
info_path = package / 'package-info.json'
info = json.loads(info_path.read_text(encoding='utf-8'))
info.update(version='20261015single1', single_instance=True)
info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
notes = '''森林小博士 · 单实例更新

同一台电脑、同一个 Windows 登录桌面，只运行一个新版森林小博士。
重复双击 EXE、VBS、CMD 或直接运行启动脚本，均复用已有程序。
从其他文件夹启动本新版副本，或者使用不同服务端口，也不会增加悬浮球。
聊天面板已打开时唤起已有面板；收起时显示已有悬浮球。
重复启动不会新建后端服务，也不会打断正在进行的回答。
程序退出或意外崩溃后，系统自动释放实例标记，可以重新启动。

首次换用此版本前，请从旧悬浮球的右键菜单选择“退出森林小博士”，
将所有旧版窗口退出，再完整解压新版并启动。旧版程序本身没有此保护。
此更新不限制不同手机或平板的扫码对话。
'''
(package / '单实例更新说明.txt').write_text(notes, encoding='utf-8-sig')
temporary = OUT / '森林小博士_本地电脑版.new.zip'
with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
    for file in package.rglob('*'):
        relative = file.relative_to(package)
        if not file.is_file() or 'data' in relative.parts or '__pycache__' in relative.parts or file.suffix == '.pyc':
            continue
        z.write(file, Path(package.name) / relative)
with zipfile.ZipFile(temporary) as z:
    assert z.testzip() is None
    assert package.name + '/desktop/single_instance.py' in z.namelist()
    assert not any('/data/' in name for name in z.namelist())
temporary.replace(OUT / '森林小博士_本地电脑版.zip')
print('Updated private classroom package:', (OUT / '森林小博士_本地电脑版.zip').stat().st_size, 'bytes')
