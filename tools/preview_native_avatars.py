"""Render the actual Win32 transcript to an offscreen DIB; no desktop input."""
import ctypes
from pathlib import Path
import sys
from unittest.mock import patch
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop'))
import win32ui as W
from bubble_transcript import BubbleTranscript

canvas=W.LayeredCanvas();canvas.ensure(520,560)
font=W.make_font(18);small=W.make_font(13)
view=BubbleTranscript(None,1,font,small)
view.hwnd=1
view.messages=[{'role':'assistant','text':'你好，我是森林小博士。\n和我一起寻找大自然里的隐身高手吧！'},
               {'role':'user','text':'你介绍一下你自己'},
               {'role':'assistant','text':'我是森林小博士，陪你探索大自然的小伙伴。我们一起找找藏起来的小动物吧！'}]
def bounds(hwnd,ptr):
    ptr._obj.left=ptr._obj.top=0;ptr._obj.right=520;ptr._obj.bottom=560
try:
    with patch.object(W.user32,'BeginPaint',return_value=canvas.hdc_mem), \
         patch.object(W.user32,'EndPaint'),patch.object(W.user32,'GetClientRect',side_effect=bounds), \
         patch.object(W.user32,'SetScrollInfo'):
        view._paint(1)
    assert len(view._avatar_images)==2
    raw=ctypes.string_at(canvas.bits,520*560*4)
    picture=Image.frombytes('RGBA',(520,560),raw,'raw','BGRA').convert('RGB')
    path=ROOT/'docs/ui-preview/森林小博士_双方头像对话.png'
    picture.save(path)
    print('Native transcript rendered; both avatar assets loaded.')
finally:
    canvas.release();W.gdi32.DeleteObject(font);W.gdi32.DeleteObject(small)
