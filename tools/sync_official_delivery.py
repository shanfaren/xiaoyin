"""Refresh the private portable delivery without copying classroom history."""
from pathlib import Path
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / '交付包'
package = OUT / '森林小博士_本地电脑版'
assert package.is_dir()
for folder in ('web', 'assets', 'desktop'):
    shutil.copytree(ROOT / folder, package / folder, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
info = json.loads((package / 'package-info.json').read_text(encoding='utf-8'))
info.update(avatar='forest-official.png', version='20261015official1',
            character_preview='rendered image; 3D mesh pending free GPU quota')
(package / 'package-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
notes = ('官方展示形象已统一为戴眼镜、穿迷彩服的森林勘探家。\n'
         '桌面悬浮球、扫码端顶部与消息头像使用同一官方头像。\n'
         '形象对话展示全身角色预览，保留语音输入、语音输出和云朵回答框。\n'
         '当前全身预览为图片，不是可旋转的3D模型；免费建模服务GPU配额耗尽，尚未生成可用模型。\n')
(package / '形象更新说明.txt').write_text(notes, encoding='utf-8-sig')
reference = OUT / '森林小博士_视频人物参考'
shutil.copy2(ROOT / 'assets/avatar/forest-explorer-preview.webp', reference / '森林小博士_全身形象预览.webp')
(reference / '官方形象说明.txt').write_text(notes, encoding='utf-8-sig')
qr = OUT / '森林小博士_扫码版'
(qr / '形象更新说明.txt').write_text(notes + '\n扫码地址不变：https://xiaoyin.onrender.com/\n', encoding='utf-8-sig')
for name in ('森林小博士_本地电脑版', '森林小博士_扫码版'):
    folder = OUT / name
    archive = OUT / (name + '.zip')
    temporary = OUT / (name + '.new.zip')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
        for file in folder.rglob('*'):
            relative = file.relative_to(folder)
            if not file.is_file() or 'data' in relative.parts or '__pycache__' in relative.parts or file.suffix == '.pyc':
                continue
            z.write(file, Path(name) / relative)
    with zipfile.ZipFile(temporary) as z:
        assert z.testzip() is None
        assert not any('/data/' in p for p in z.namelist())
    temporary.replace(archive)
    print(archive.name, archive.stat().st_size)
