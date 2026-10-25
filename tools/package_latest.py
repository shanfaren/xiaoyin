"""Maintain exactly two clearly named latest delivery folders."""
from pathlib import Path
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'交付包'
LOCAL=OUT/'森林小博士—电脑本地版'
CLOUD=OUT/'森林小博士—云端版'
assert LOCAL.is_dir() and CLOUD.is_dir()
for folder in ('desktop','web','assets','backend'):
    shutil.copytree(ROOT/folder,LOCAL/folder,dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
info_path=LOCAL/'package-info.json'
info=json.loads(info_path.read_text(encoding='utf-8'))
info.update(name='森林小博士—电脑本地版',version='20261016blender1',single_instance=True,
            runtime_selection='bundled_only',requires_installed_python=False,
            character_preview='cloud Blender skeletal GLB; desktop native avatar chat',
            voice_profile='forest-doctor-male-v1')
info_path.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
limitations=('已实测：交付包自带运行时、本机HTTP服务、真实语音识别、真实AI回答、清爽男声合成和单实例保护。\n'
    '当前验收使用合成测试音频，不代表已测试教室实体麦克风、音箱或另一台多媒体电脑。\n')
manual='''森林小博士—电脑本地版

适用：Windows 10/11 64位多媒体电脑、希沃白板和PPT课堂展示。
自带运行环境，无需安装Python或浏览器插件，无需管理员安装。
把整个压缩包复制到教室电脑，先全部解压到可写的桌面或文档目录。
不能直接在压缩包中启动，不能只复制单个EXE。
双击“启动森林小博士—电脑本地版.exe”，显示原生桌面悬浮球。
同一 Windows 登录桌面只运行一个实例，重复启动会唤起已有窗口。
重复双击启动程序会直接展开同一个聊天面板，不会再创建一个智能体。
首次使用新版前，从旧悬浮球右键菜单退出所有旧程序。
提问答疑（直接解释）、探究提示（先给线索）两个入口；支持文字、语音输入及男声朗读。
语音按钮：按住说话，松开结束；误触不足0.35秒自动取消，最长60秒。
录音中文字约每3秒请求更新，网络识别可能稍有延迟；松开后用完整录音最终识别并发送提问。
聊天中左侧为森林小博士官方头像，右侧为通用卡通用户头像。
API配置已带入，无需重新填写；此文件夹含私密API配置，仅复制到可信电脑，勿公开上传。
需要联网调用AI和语音接口；本地版不是离线大模型。
手机扫码端的新模型使用Blender真实骨骼与下颌；电脑本地版使用原生悬浮球与头像聊天。
复制到其他电脑时，使用同目录的“森林小博士—电脑本地版.zip”，完整解压后启动。
麦克风和扬声器需可用，Windows需允许桌面应用访问麦克风。
课前先连接教室音箱或交互大屏，在Windows中选好实际的麦克风与扬声器。
打开希沃课件后再启动本程序；需要时点击“置顶”，点击减号收起为悬浮球。
日志与本机对话保存在data目录，打包文件不包含已有对话记录。
'''
if limitations: manual+='\n运行环境验收说明：\n'+limitations
(LOCAL/'使用说明.txt').write_text(manual,encoding='utf-8-sig')
shutil.copy2(ROOT/'assets/audio/森林小博士_统一标准试听.mp3', LOCAL/'森林小博士_统一标准试听.mp3')
shutil.copy2(ROOT/'assets/audio/森林小博士_统一标准试听.json', LOCAL/'统一音色参数.json')
old_preview=LOCAL/'森林小博士_清爽男声试听.mp3'
if old_preview.exists(): old_preview.unlink()
(LOCAL/'统一音色说明.txt').write_text('''森林小博士统一声音
音色ID：zh_male_taocheng_uranus_bigtts
模型：seed-tts-2.0；语速参数：-5（约0.95倍）
风格：清爽、明亮、亲切的年轻男声；吐字清楚、轻快温和。
现场回答与视频台词配音均使用backend/voice_profile.py中的唯一规范。
不使用系统备用声音。视频动画文件保持静音，由同一个语音接口配音。
标准试听：森林小博士_统一标准试听.mp3。
后续视频台词配音：runtime\\python.exe tools\\synthesize_character_speech.py --text "台词" --output "台词.mp3"
''',encoding='utf-8-sig')
(LOCAL/'tools').mkdir(exist_ok=True)
shutil.copy2(ROOT/'tools/synthesize_character_speech.py',LOCAL/'tools/synthesize_character_speech.py')
old_exe=LOCAL/'启动森林小博士.exe';new_exe=LOCAL/'启动森林小博士—电脑本地版.exe'
if old_exe.exists():old_exe.replace(new_exe)
old_qr=CLOUD/'森林小博士_扫码体验.png';new_qr=CLOUD/'森林小博士—云端版二维码.png'
if old_qr.exists():old_qr.replace(new_qr)
old_url=CLOUD/'打开森林小博士.url';new_url=CLOUD/'打开森林小博士—云端版.url'
if old_url.exists():old_url.replace(new_url)
(CLOUD/'使用说明.txt').write_text('''森林小博士—云端版

手机或平板扫描“森林小博士—云端版二维码.png”，或者双击网页快捷方式。
访问地址：https://xiaoyin.onrender.com/?v=20261016blender1
支持形象对话与文字聊天，语音输入和清爽男声输出。
不同手机、平板分别对话；无需安装电脑本地版。
3D对话模式：新版模型由Blender制作，骨骼带动手臂，下颌随实际播放声音开合；云朵显示当前回答。
本地模型已完成；云端是否更新请以本文件夹的“发布状态.txt”为准。
首次使用语音需允许浏览器使用麦克风。
''',encoding='utf-8-sig')
# Only generated duplicate notices are removed; conversation data is untouched.
for folder,names in ((LOCAL,['单实例更新说明.txt','男声更新说明.txt','形象更新说明.txt','验收说明.txt']),
                     (CLOUD,['形象更新说明.txt','森林小博士_扫码体验.svg'])):
    for name in names:
        file=folder/name
        if file.exists():file.unlink()
archive=LOCAL/'森林小博士—电脑本地版.zip'
temporary=OUT/'latest-local.new.zip'
with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
    for file in LOCAL.rglob('*'):
        relative=file.relative_to(LOCAL)
        if not file.is_file() or file==archive or 'data' in relative.parts or '__pycache__' in relative.parts or file.suffix=='.pyc':continue
        z.write(file,Path(LOCAL.name)/relative)
with zipfile.ZipFile(temporary) as z:
    assert z.testzip() is None
    assert LOCAL.name+'/assets/avatar/user-cartoon.png' in z.namelist()
    assert LOCAL.name+'/desktop/single_instance.py' in z.namelist()
    assert not any('/data/' in name for name in z.namelist())
temporary.replace(archive)
assert {p.name for p in OUT.iterdir()}=={LOCAL.name,CLOUD.name}
print('Latest computer and cloud delivery folders verified.')
