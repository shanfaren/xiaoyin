"""Prepare the approved explorer portrait and update all avatar surfaces."""
from pathlib import Path
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'D:\Codex\chatgpt-home\generated_images\01a13d87-accb-7081-ad0c-9e1eb92da8a2\exec-7c14c8e1-2674-422d-ba89-74b9a7a69096.png')
target = ROOT / 'assets/avatar/forest-official.png'
image = Image.open(SOURCE).convert('RGBA')
bounds = image.getbbox()
portrait = image.crop(bounds)
side = max(portrait.size)
canvas = Image.new('RGBA', (side, side))
canvas.alpha_composite(portrait, ((side - portrait.width)//2, (side - portrait.height)//2))
canvas.resize((256, 256), Image.Resampling.LANCZOS).save(target, optimize=True)
delivery = ROOT.parent / '交付包/森林小博士_视频人物参考'
shutil.copy2(SOURCE, delivery / '森林小博士_官方头像原图.png')
shutil.copy2(target, delivery / '森林小博士_官方头像.png')

app = ROOT / 'web/app.js'
text = app.read_text(encoding='utf-8')
start = text.index('  /* ---------- 角色头像')
end = text.index('  /* ---------- 状态', start)
text = text[:start] + '''  /* 官方勘探家头像；与桌面悬浮球使用同一资产。 */
  var AVATAR_SVG = '<img src="/assets/avatar/forest-official.png?v=20261015official1" alt="森林小博士" loading="lazy">';

''' + text[end:]
text = text.replace("img.src = '/assets/avatar/xiaoyin_' + state + '.svg';", "img.dataset.state = state;\n      img.parentElement.dataset.state = state;")
text = text.replace('// 资产缺失时退回内联 SVG（离线可用）', '// 图片不可用时保留角色名称，避免无限重试。')
text = text.replace("if (box && !box.querySelector('svg')) box.innerHTML = AVATAR_SVG;", "if (box) { box.textContent = '森林'; box.setAttribute('aria-label', '森林小博士'); }")
app.write_text(text, encoding='utf-8')
index = ROOT / 'web/index.html'
text = index.read_text(encoding='utf-8').replace('/assets/avatar/xiaoyin_idle.svg', '/assets/avatar/forest-official.png?v=20261015official1')
text = text.replace('20261015dual3', '20261015official1').replace('chat.css?v=', 'chat.css?v=')
# Bump the existing style query regardless of its preceding version.
import re
text = re.sub(r'chat\.css\?v=[^"\s]+', 'chat.css?v=20261015official1', text)
index.write_text(text, encoding='utf-8')
floating = ROOT / 'desktop/floating.py'
text = floating.read_text(encoding='utf-8')
text = text.replace("p = os.path.join(AVATAR_DIR, 'xiaoyin_%s_%s.png' % (state, suffix))\n                if not os.path.isfile(p):\n                    p = os.path.join(AVATAR_DIR, 'xiaoyin_%s.png' % state)", "p = os.path.join(AVATAR_DIR, 'forest-official.png')")
text = text.replace('保留森林小博士角色与状态动画', '保留官方勘探家头像的透明边缘')
floating.write_text(text, encoding='utf-8')
print('Official avatar prepared:', target.stat().st_size, 'bytes; alpha', canvas.getextrema()[3])
