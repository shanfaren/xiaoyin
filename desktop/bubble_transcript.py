"""Win32 原生、多轮消息气泡；不使用浏览器或网页容器。"""
import ctypes
import ctypes.wintypes as wt
from pathlib import Path
import pngio
import win32ui as W


class PAINTSTRUCT(ctypes.Structure):
    _fields_=[('hdc',wt.HDC),('erase',wt.BOOL),('rect',W.RECT),('restore',wt.BOOL),
              ('inc',wt.BOOL),('reserved',ctypes.c_byte*32)]


class SCROLLINFO(ctypes.Structure):
    _fields_=[('size',wt.UINT),('mask',wt.UINT),('minimum',ctypes.c_int),
              ('maximum',ctypes.c_int),('page',wt.UINT),('position',ctypes.c_int),('track',ctypes.c_int)]


W.user32.BeginPaint.argtypes=[wt.HWND,ctypes.c_void_p]
W.user32.BeginPaint.restype=wt.HDC
W.user32.EndPaint.argtypes=[wt.HWND,ctypes.c_void_p]
W.user32.FillRect.argtypes=[wt.HDC,ctypes.POINTER(W.RECT),wt.HBRUSH]
W.user32.DrawTextW.argtypes=[wt.HDC,wt.LPCWSTR,ctypes.c_int,ctypes.POINTER(W.RECT),wt.UINT]
W.user32.SetScrollInfo.argtypes=[wt.HWND,ctypes.c_int,ctypes.POINTER(SCROLLINFO),wt.BOOL]
W.user32.GetScrollInfo.argtypes=[wt.HWND,ctypes.c_int,ctypes.POINTER(SCROLLINFO)]
W.gdi32.CreateCompatibleBitmap.argtypes=[wt.HDC,ctypes.c_int,ctypes.c_int]
W.gdi32.CreateCompatibleBitmap.restype=wt.HBITMAP
W.gdi32.BitBlt.argtypes=[wt.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wt.HDC,ctypes.c_int,ctypes.c_int,wt.DWORD]
W.gdi32.CreatePen.argtypes=[ctypes.c_int,ctypes.c_int,wt.COLORREF]
W.gdi32.CreatePen.restype=wt.HANDLE
W.gdi32.RoundRect.argtypes=[wt.HDC]+[ctypes.c_int]*6
W.gdi32.SetDIBitsToDevice.argtypes=[wt.HDC,ctypes.c_int,ctypes.c_int,wt.DWORD,wt.DWORD,
    ctypes.c_int,ctypes.c_int,wt.UINT,wt.UINT,ctypes.c_void_p,ctypes.POINTER(W.BITMAPINFO),wt.UINT]
W.gdi32.SetDIBitsToDevice.restype=ctypes.c_int


class BubbleTranscript:
    def __init__(self,parent,scale,font,small_font):
        self.parent=parent
        self.scale=scale
        self.font=font
        self.small_font=small_font
        self.messages=[]
        self.offset=0
        self.total=0
        self.height=0
        self.follow_bottom=True
        self.hwnd=None
        self._avatar_images={}
        self.proc=W.WNDPROC(self._wndproc)

    def s(self,value): return int(round(value*self.scale))

    def create(self,x,y,width,height):
        wc=W.WNDCLASSEXW(); wc.cbSize=ctypes.sizeof(wc)
        wc.lpfnWndProc=ctypes.cast(self.proc,ctypes.c_void_p)
        wc.hInstance=W.kernel32.GetModuleHandleW(None)
        wc.hCursor=W.user32.LoadCursorW(None,ctypes.c_wchar_p(W.IDC_ARROW))
        wc.lpszClassName='XiaoyinBubbleTranscript'
        if not W.user32.RegisterClassExW(ctypes.byref(wc)) and W.kernel32.GetLastError()!=1410:
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd=W.user32.CreateWindowExW(0,wc.lpszClassName,'森林小博士的多轮对话',
            W.WS_CHILD|W.WS_VISIBLE|W.WS_VSCROLL,self.s(x),self.s(y),self.s(width),self.s(height),
            self.parent,None,wc.hInstance,None)
        if not self.hwnd: raise ctypes.WinError(ctypes.get_last_error())
        return self.hwnd

    def append(self,text):
        if text.startswith('我：'):
            self.messages.append({'role':'user','text':text[2:].strip()})
        elif text.strip():
            if self.messages and self.messages[-1]['role']=='assistant':
                self.messages[-1]['text']+=text
            else:
                self.messages.append({'role':'assistant','text':text.lstrip()})
        self.follow_bottom=True
        W.user32.InvalidateRect(self.hwnd,None,False)

    def clear(self):
        self.messages=[]; self.offset=0
        W.user32.InvalidateRect(self.hwnd,None,False)

    def _text(self,dc,text,rect,font,color,flags=0x10):
        old=W.gdi32.SelectObject(dc,font)
        W.gdi32.SetBkMode(dc,W.TRANSPARENT)
        W.gdi32.SetTextColor(dc,W.rgb(*color))
        r=W.RECT(*rect)
        W.user32.DrawTextW(dc,text,-1,ctypes.byref(r),flags)
        W.gdi32.SelectObject(dc,old)
        return r

    def _round(self,dc,rect,color):
        brush=W.gdi32.CreateSolidBrush(W.rgb(*color)); pen=W.gdi32.CreatePen(0,1,W.rgb(*color))
        old_b=W.gdi32.SelectObject(dc,brush); old_p=W.gdi32.SelectObject(dc,pen)
        W.gdi32.RoundRect(dc,*rect,self.s(18),self.s(18))
        W.gdi32.SelectObject(dc,old_b); W.gdi32.SelectObject(dc,old_p)
        W.gdi32.DeleteObject(brush); W.gdi32.DeleteObject(pen)

    def _avatar(self,dc,role,x,y):
        size=self.s(36)
        key=(role,size)
        if key not in self._avatar_images:
            filename='user-cartoon.png' if role=='user' else 'forest-official.png'
            path=Path(__file__).resolve().parents[1]/'assets'/'avatar'/filename
            width,height,rows=pngio.decode_png(str(path))
            rows=pngio.scale_rows(rows,width,height,size,size)
            pixels=bytearray(size*size*4)
            background=(255,250,243)
            badge=(229,237,245) if role=='user' else (237,235,219)
            center=(size-1)/2
            for py,row in enumerate(rows):
                for px in range(size):
                    coverage=max(0,min(1,size/2-((px-center)**2+(py-center)**2)**.5))
                    base=[int(badge[c]*coverage+background[c]*(1-coverage)) for c in range(3)]
                    alpha=row[px*4+3]/255*coverage
                    rgb=[int(row[px*4+c]*alpha+base[c]*(1-alpha)) for c in range(3)]
                    i=(py*size+px)*4
                    pixels[i:i+4]=bytes((rgb[2],rgb[1],rgb[0],255))
            info=W.BITMAPINFO(); info.bmiHeader.biSize=ctypes.sizeof(W.BITMAPINFOHEADER)
            info.bmiHeader.biWidth=size; info.bmiHeader.biHeight=-size
            info.bmiHeader.biPlanes=1; info.bmiHeader.biBitCount=32
            self._avatar_images[key]=(info,ctypes.create_string_buffer(bytes(pixels)))
        info,pixels=self._avatar_images[key]
        W.gdi32.SetDIBitsToDevice(dc,x,y,size,size,0,0,0,size,pixels,ctypes.byref(info),W.DIB_RGB_COLORS)

    def _paint(self,hwnd):
        ps=PAINTSTRUCT(); screen=W.user32.BeginPaint(hwnd,ctypes.byref(ps))
        bounds=W.RECT(); W.user32.GetClientRect(hwnd,ctypes.byref(bounds))
        width,height=bounds.right,bounds.bottom
        if width<=0 or height<=0:
            W.user32.EndPaint(hwnd,ctypes.byref(ps)); return
        dc=W.gdi32.CreateCompatibleDC(screen)
        bitmap=W.gdi32.CreateCompatibleBitmap(screen,width,height)
        old_bitmap=W.gdi32.SelectObject(dc,bitmap)
        brush=W.gdi32.CreateSolidBrush(W.rgb(255,250,243))
        try:
            W.user32.FillRect(dc,ctypes.byref(bounds),brush)
            layouts=[]; y=self.s(8); pad=self.s(12)
            avatar_size=self.s(36); gap=self.s(10); margin=self.s(6)
            max_width=max(self.s(65),min(int(width*.78),width-2*(margin+avatar_size+gap)))
            for message in self.messages:
                text=message['text'].strip()
                if not text: continue
                measured=self._text(dc,text,(0,0,max_width-pad*2,0),self.font,(35,42,36),0x10|0x400|0x800)
                bubble_width=min(max_width,max(self.s(65),measured.right+pad*2))
                bubble_height=max(self.s(43),measured.bottom+pad*2)
                x=width-margin-avatar_size-gap-bubble_width if message['role']=='user' else margin+avatar_size+gap
                layouts.append((message,x,y,bubble_width,bubble_height))
                y+=max(bubble_height,avatar_size)+self.s(34)
            self.total=y; self.height=height
            maximum=max(0,y-height)
            self.offset=maximum if self.follow_bottom else min(self.offset,maximum)
            self.follow_bottom=False
            info=SCROLLINFO(ctypes.sizeof(SCROLLINFO),0x7,0,max(0,y-1),height,self.offset,0)
            W.user32.SetScrollInfo(hwnd,1,ctypes.byref(info),True)
            for message,x,y,bw,bh in layouts:
                top=y-self.offset
                if top+bh<0 or top>height: continue
                color=(226,240,228) if message['role']=='user' else (255,255,255)
                avatar_x=width-margin-avatar_size if message['role']=='user' else margin
                self._avatar(dc,message['role'],avatar_x,top)
                self._round(dc,(x,top,x+bw,top+bh),color)
                self._text(dc,message['text'].strip(),(x+pad,top+pad,x+bw-pad,top+bh-pad),self.font,(35,42,36),0x10|0x800)
                self._text(dc,'我' if message['role']=='user' else '森林小博士',
                    (x,top+bh+self.s(3),x+bw,top+bh+self.s(22)),self.small_font,(139,137,128),0x20|(2 if message['role']=='user' else 0))
            W.gdi32.BitBlt(screen,0,0,width,height,dc,0,0,W.SRCCOPY)
        finally:
            W.gdi32.SelectObject(dc,old_bitmap)
            W.gdi32.DeleteObject(bitmap); W.gdi32.DeleteObject(brush); W.gdi32.DeleteDC(dc)
            W.user32.EndPaint(hwnd,ctypes.byref(ps))

    def _scroll(self,value):
        self.follow_bottom=False
        self.offset=max(0,min(max(0,self.total-self.height),value))
        W.user32.InvalidateRect(self.hwnd,None,False)

    def _wndproc(self,hwnd,msg,wp,lp):
        if msg==W.WM_PAINT:
            self._paint(hwnd); return 0
        if msg==W.WM_ERASEBKGND: return 1
        if msg==W.WM_MOUSEWHEEL:
            delta=W.hiword(wp); delta=delta-65536 if delta>=32768 else delta
            self._scroll(self.offset-int(delta/120)*self.s(48)); return 0
        if msg==W.WM_VSCROLL:
            code=W.loword(wp)
            if code in (4,5):
                info=SCROLLINFO(); info.size=ctypes.sizeof(info); info.mask=0x10
                W.user32.GetScrollInfo(hwnd,1,ctypes.byref(info)); target=info.track
            else:
                target=self.offset+{0:-self.s(32),1:self.s(32),2:-self.height,3:self.height,6:-self.total,7:self.total}.get(code,0)
            self._scroll(target); return 0
        if msg==0x0005:
            self.follow_bottom=True
            W.user32.InvalidateRect(hwnd,None,False); return 0
        return W.user32.DefWindowProcW(hwnd,msg,wp,lp)
