"""Update the private desktop distribution and preserve its singleton fix."""
from pathlib import Path
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / '交付包'
package = OUT / '森林小博士_本地电脑版'
for name in ('config.py', 'adapters/tts.py'):
    shutil.copy2(ROOT / 'backend' / name, package / 'backend' / name)
source = json.loads((ROOT / 'config/config.json').read_text(encoding='utf-8'))
config_path = package / 'config/config.json'
config = json.loads(config_path.read_text(encoding='utf-8'))
for name in ('voice', 'speech_rate', 'context_texts'):
    config['tts'][name] = source['tts'][name]
config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
info_path = package / 'package-info.json'
info = json.loads(info_path.read_text(encoding='utf-8'))
info.update(version='20261015male1', voice=source['tts']['voice'])
assert info['single_instance'] is True
info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
preview = OUT / '森林小博士_清爽男声试听.mp3'
shutil.copy2(ROOT / 'data/forest_male_voice_preview.mp3', preview)
shutil.copy2(preview, package / preview.name)
(package / '男声更新说明.txt').write_text(
    '默认语音已更换为清爽青年男声，与森林小博士的男生头像保持一致。\n'
    '默认音色：zh_male_taocheng_uranus_bigtts。\n'
    '语气亲切、明亮，适合课堂讲解；打开随包试听文件可听效果。\n'
    '已保留单实例保护。退出旧程序后启动此新版即可生效，无需重新填写API。\n', encoding='utf-8-sig')
temporary = OUT / '森林小博士_本地电脑版.new.zip'
with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
    for file in package.rglob('*'):
        relative = file.relative_to(package)
        if not file.is_file() or 'data' in relative.parts or '__pycache__' in relative.parts or file.suffix == '.pyc':
            continue
        z.write(file, Path(package.name) / relative)
with zipfile.ZipFile(temporary) as z:
    assert z.testzip() is None
    packaged = json.loads(z.read(package.name + '/config/config.json'))
    assert packaged['tts']['voice'] == source['tts']['voice']
    assert package.name + '/desktop/single_instance.py' in z.namelist()
temporary.replace(OUT / '森林小博士_本地电脑版.zip')
print('Male voice packaged; singleton retained; private credentials unchanged.')
