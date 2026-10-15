# -*- coding: utf-8 -*-
"""Win32 API 绑定与助手（纯 ctypes，无第三方依赖）。

仅覆盖本项目需要的部分：
- 窗口类注册 / 创建 / 消息循环（user32、kernel32）
- 分层窗口（WS_EX_LAYERED + UpdateLayeredWindow）实现逐像素透明
- 菜单（右键弹出菜单）、计时器、工具提示
- GDI 位图与内存 DC
- 音频：waveIn 录音（winmm）、MCI 播放（winmm）
- 线程消息投递（PostMessage）

注意：本模块不修改任何系统设置（不碰代理、防火墙、注册表安全项）。
"""
import ctypes
import ctypes.wintypes as wt
import sys

if sys.platform != 'win32':
    raise RuntimeError('desktop 模块仅支持 Windows')

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
shell32 = ctypes.WinDLL('shell32', use_last_error=True)
comctl32 = ctypes.WinDLL('comctl32', use_last_error=True)
winmm = ctypes.WinDLL('winmm', use_last_error=True)

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
UINT = ctypes.c_uint

# ------------------------------------------------------------------ 常量
WS_OVERLAPPED = 0x00000000
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CLIPSIBLINGS = 0x04000000
WS_CLIPCHILDREN = 0x02000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_VSCROLL = 0x00200000
WS_HSCROLL = 0x00100000
WS_BORDER = 0x00800000
WS_TABSTOP = 0x00010000
WS_OVERLAPPEDWINDOW = (WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME
                       | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)

WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000

ES_MULTILINE = 0x0004
ES_AUTOVSCROLL = 0x0040
ES_AUTOHSCROLL = 0x0080
ES_READONLY = 0x0800
ES_WANTRETURN = 0x1000
ES_NOHIDESEL = 0x0100
ES_LEFT = 0x0000

BS_PUSHBUTTON = 0x00000000
BS_DEFPUSHBUTTON = 0x00000001
BS_AUTOCHECKBOX = 0x00000003

CBS_DROPDOWNLIST = 0x0003
CBS_HASSTRINGS = 0x0200
CBS_NOINTEGRALHEIGHT = 0x0400

SS_LEFT = 0x00000000
SS_RIGHT = 0x00000002
SS_CENTER = 0x00000001
SS_NOPREFIX = 0x00000080

LBS_NOTIFY = 0x0001
LBS_NOINTEGRALHEIGHT = 0x0100
LBS_HASSTRINGS = 0x0040

SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNORMAL = 1
SW_SHOWNOACTIVATE = 4

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_COMMAND = 0x0111
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_TIMER = 0x0113
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
WM_RBUTTONDOWN = 0x0204
WM_NCHITTEST = 0x0084
WM_SETCURSOR = 0x0020
WM_CTLCOLORSTATIC = 0x0138
WM_CTLCOLOREDIT = 0x0133
WM_CTLCOLORBTN = 0x0135
WM_CTLCOLORLISTBOX = 0x0134
WM_GETMINMAXINFO = 0x0024
WM_APP = 0x8000
WM_SYSCOMMAND = 0x0112
WM_KEYDOWN = 0x0100
WM_CHAR = 0x0102
WM_SETFONT = 0x0030
WM_DROPFILES = 0x0233
WM_MOUSEWHEEL = 0x020A
WM_VSCROLL = 0x0115

HTCLIENT = 1
HTCAPTION = 2

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_GRAYED = 0x00000001
MF_CHECKED = 0x00000008

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0

SPI_GETWORKAREA = 0x0030
SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_CXSMICON = 49

COLOR_WINDOW = 5
COLOR_BTNFACE = 15
TRANSPARENT = 1

GWLP_USERDATA = -21
GWL_EXSTYLE = -20
GWL_STYLE = -16
GWL_WNDPROC = -4
GWLP_WNDPROC = -4
GWLP_HINSTANCE = -6
GWLP_ID = -12

IDC_ARROW = 32512
IDC_HAND = 32649

SRCCOPY = 0x00CC0020

# 自定义消息：跨线程投递
WM_XY_STATE = WM_APP + 1        # 悬浮窗状态变化（wParam 为状态编号）
WM_XY_LOG = WM_APP + 2          # 对话框：追加文本
WM_XY_STATUS = WM_APP + 3       # 对话框：更新状态栏
WM_XY_STAGES = WM_APP + 4       # 对话框：教学环节列表就绪
WM_XY_CAPS = WM_APP + 5         # 对话框：能力状态就绪
WM_XY_ASR = WM_APP + 6          # 对话框：语音识别结果
WM_XY_TRAY = WM_APP + 7         # 悬浮窗：需要打开对话框

# ------------------------------------------------------------------ 结构体


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ('cbSize', UINT), ('style', UINT), ('lpfnWndProc', ctypes.c_void_p),
        ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
        ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON), ('hCursor', wt.HANDLE),
        ('hbrBackground', wt.HBRUSH), ('lpszMenuName', wt.LPCWSTR),
        ('lpszClassName', wt.LPCWSTR), ('hIconSm', wt.HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, UINT, WPARAM, LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [('cx', ctypes.c_long), ('cy', ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [('BlendOp', ctypes.c_ubyte), ('BlendFlags', ctypes.c_ubyte),
                ('SourceConstantAlpha', ctypes.c_ubyte), ('AlphaFormat', ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', ctypes.c_long), ('biHeight', ctypes.c_long),
                ('biPlanes', wt.WORD), ('biBitCount', wt.WORD), ('biCompression', wt.DWORD),
                ('biSizeImage', wt.DWORD), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', wt.DWORD),
                ('biClrImportant', wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wt.DWORD * 3)]


class MSG(ctypes.Structure):
    _fields_ = [('hwnd', wt.HWND), ('message', UINT), ('wParam', WPARAM),
                ('lParam', LPARAM), ('time', wt.DWORD), ('pt', POINT)]


class WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('wFormatTag', wt.WORD), ('nChannels', wt.WORD),
                ('nSamplesPerSec', wt.DWORD), ('nAvgBytesPerSec', wt.DWORD),
                ('nBlockAlign', wt.WORD), ('wBitsPerSample', wt.WORD),
                ('cbSize', wt.WORD)]


class WAVEHDR(ctypes.Structure):
    _fields_ = [('lpData', ctypes.c_void_p), ('dwBufferLength', wt.DWORD),
                ('dwBytesRecorded', wt.DWORD), ('dwUser', ctypes.c_void_p),
                ('dwFlags', wt.DWORD), ('dwLoops', wt.DWORD),
                ('lpNext', ctypes.c_void_p), ('reserved', ctypes.c_void_p)]


class INITCOMMONCONTROLSEX(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('dwICC', wt.DWORD)]


class TOOLINFO(ctypes.Structure):
    _fields_ = [('cbSize', UINT), ('uFlags', UINT), ('hwnd', wt.HWND),
                ('uId', ctypes.c_size_t), ('rect', RECT), ('hinst', wt.HINSTANCE),
                ('lpszText', wt.LPWSTR), ('lParam', LPARAM)]


# ------------------------------------------------------------------ 函数原型
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wt.WORD
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p]
user32.CreateWindowExW.restype = wt.HWND
user32.DefWindowProcW.argtypes = [wt.HWND, UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, UINT, UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostMessageW.argtypes = [wt.HWND, UINT, WPARAM, LPARAM]
user32.SendMessageW.argtypes = [wt.HWND, UINT, WPARAM, LPARAM]
user32.SendMessageW.restype = LRESULT
user32.DestroyWindow.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.UpdateWindow.argtypes = [wt.HWND]
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, UINT]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowTextW.argtypes = [wt.HWND, wt.LPCWSTR]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.LoadCursorW.argtypes = [wt.HINSTANCE, wt.LPCWSTR]
user32.LoadCursorW.restype = wt.HANDLE
user32.SetCursor.argtypes = [wt.HANDLE]
user32.SetCapture.argtypes = [wt.HWND]
user32.ReleaseCapture.argtypes = []
user32.SystemParametersInfoW.argtypes = [UINT, UINT, ctypes.c_void_p, UINT]
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wt.HMENU, UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wt.HWND, ctypes.c_void_p]
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, UINT, ctypes.c_void_p]
user32.KillTimer.argtypes = [wt.HWND, ctypes.c_size_t]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.MessageBoxW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, UINT]
user32.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(RECT), wt.BOOL]
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.mouse_event.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
user32.EnableWindow.argtypes = [wt.HWND, wt.BOOL]
user32.SetFocus.argtypes = [wt.HWND]
user32.EnumChildWindows.argtypes = [wt.HWND, ctypes.c_void_p, LPARAM]
user32.EnableMenuItem.argtypes = [wt.HMENU, UINT, UINT]
user32.DrawMenuBar.argtypes = [wt.HWND]
user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wt.HWND, UINT, WPARAM, LPARAM]
user32.CallWindowProcW.restype = LRESULT
user32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
user32.GetDlgItem.restype = wt.HWND
user32.SetWindowTextW.restype = wt.BOOL
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.CreateSolidBrush.argtypes = [wt.COLORREF]
gdi32.CreateSolidBrush.restype = wt.HBRUSH
gdi32.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD,
                              wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR]
gdi32.CreateFontW.restype = wt.HFONT
gdi32.SetTextColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetBkColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]
gdi32.GetDeviceCaps.restype = ctypes.c_int

user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(POINT),
                                       ctypes.POINTER(SIZE), wt.HDC, ctypes.POINTER(POINT),
                                       wt.COLORREF, ctypes.POINTER(BLENDFUNCTION), wt.DWORD]

comctl32.InitCommonControlsEx.argtypes = [ctypes.POINTER(INITCOMMONCONTROLSEX)]
comctl32.InitCommonControlsEx.restype = wt.BOOL

winmm.waveInGetNumDevs.restype = UINT
winmm.waveInOpen.argtypes = [ctypes.POINTER(wt.HANDLE), UINT, ctypes.POINTER(WAVEFORMATEX),
                             ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]
winmm.waveInPrepareHeader.argtypes = [wt.HANDLE, ctypes.POINTER(WAVEHDR), UINT]
winmm.waveInUnprepareHeader.argtypes = [wt.HANDLE, ctypes.POINTER(WAVEHDR), UINT]
winmm.waveInAddBuffer.argtypes = [wt.HANDLE, ctypes.POINTER(WAVEHDR), UINT]
winmm.waveInStart.argtypes = [wt.HANDLE]
winmm.waveInStop.argtypes = [wt.HANDLE]
winmm.waveInReset.argtypes = [wt.HANDLE]
winmm.waveInClose.argtypes = [wt.HANDLE]
winmm.mciSendStringW.argtypes = [wt.LPCWSTR, wt.LPWSTR, UINT, wt.HWND]
winmm.mciSendStringW.restype = wt.DWORD

kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetLastError.restype = wt.DWORD
kernel32.SetErrorMode.argtypes = [UINT]

# 常用值
WAVE_MAPPER = ctypes.c_uint(-1).value
WAVE_FORMAT_PCM = 1
CALLBACK_NULL = 0
WAVEHDR_FLAG_DONE = 0x00000001
WHDR_PREPARED = 0x00000002


# ------------------------------------------------------------------ 助手
def rgb(r, g, b):
    """COLORREF = 0x00BBGGRR（RGB 宏在 GDI 中为宏，非导出函数）。"""
    return int(r) | (int(g) << 8) | (int(b) << 16)


def loword(v):
    return v & 0xFFFF


def hiword(v):
    return (v >> 16) & 0xFFFF


def get_x_lparam(lp):
    """等价于 Win32 的 GET_X_LPARAM：按**有符号** 16 位解析客户端 x 坐标。"""
    v = lp & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def get_y_lparam(lp):
    """等价于 Win32 的 GET_Y_LPARAM：按**有符号** 16 位解析客户端 y 坐标。"""
    v = (lp >> 16) & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def get_work_area():
    """返回主显示器工作区 (left, top, right, bottom)，排除任务栏。"""
    r = RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
        return r.left, r.top, r.right, r.bottom
    return 0, 0, user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)


def init_common_controls():
    icc = INITCOMMONCONTROLSEX()
    icc.dwSize = ctypes.sizeof(INITCOMMONCONTROLSEX)
    icc.dwICC = 0x0000FFFF
    return comctl32.InitCommonControlsEx(ctypes.byref(icc))


def make_font(size_px, name='Microsoft YaHei', bold=False, italic=False):
    return gdi32.CreateFontW(-size_px, 0, 0, 0,
                             700 if bold else 400,
                             int(bool(italic)), 0, 0, 0, 0, 0, 0, 0, name)


def pump_messages():
    """阻塞式消息循环，返回退出码。"""
    msg = MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return msg.wParam


def is_topmost(hwnd):
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    return bool(int(ex or 0) & WS_EX_TOPMOST)


def send_string(hwnd, msg, text, wparam=0):
    """向**本进程内**的控件发送带字符串参数的消息（EM_REPLACESEL / CB_ADDSTRING 等）。

    这些消息不属于系统编组消息，LPARAM 必须是目标进程内的有效地址；
    由于控件与调用方同进程，直接把 Python 缓冲区的地址作为整数传入即可。
    （SendMessageW 的 LPARAM 声明为整数，传 c_wchar_p 会抛 ArgumentError。）
    """
    buf = ctypes.create_unicode_buffer(text)
    return user32.SendMessageW(hwnd, msg, wparam, ctypes.cast(buf, ctypes.c_void_p).value)


def window_rect(hwnd):
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def set_foreground(hwnd):
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


# ------------------------------------------------------------------ 分层窗口绘制
class LayeredCanvas:
    """32bpp 分层窗口画布：逐像素透明（premultiplied alpha）。"""

    def __init__(self):
        self.hdc_screen = None
        self.hdc_mem = None
        self.hbitmap = None
        self.old_bitmap = None
        self.bits = None
        self.width = 0
        self.height = 0

    def ensure(self, width, height):
        if self.width == width and self.height == height and self.hdc_mem:
            return
        self.release()
        self.width, self.height = width, height
        self.hdc_screen = user32.GetDC(None)
        self.hdc_mem = gdi32.CreateCompatibleDC(self.hdc_screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height          # 自顶向下
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        pbits = ctypes.c_void_p()
        self.hbitmap = gdi32.CreateDIBSection(self.hdc_mem, ctypes.byref(bmi), DIB_RGB_COLORS,
                                              ctypes.byref(pbits), None, 0)
        self.bits = ctypes.cast(pbits, ctypes.POINTER(ctypes.c_ubyte))
        self.old_bitmap = gdi32.SelectObject(self.hdc_mem, self.hbitmap)

    def blit_rgba(self, rgba_rows, ox=0, oy=0):
        """把 RGBA 行数据（straight alpha）写入画布并预乘 alpha。"""
        w = self.width
        for y, row in enumerate(rgba_rows):
            yy = oy + y
            if yy < 0 or yy >= self.height:
                continue
            base = yy * w * 4
            for x in range(min(w - ox, len(row) // 4)):
                xx = ox + x
                r, g, b, a = row[x * 4], row[x * 4 + 1], row[x * 4 + 2], row[x * 4 + 3]
                i = base + xx * 4
                self.bits[i] = (b * a) // 255
                self.bits[i + 1] = (g * a) // 255
                self.bits[i + 2] = (r * a) // 255
                self.bits[i + 3] = a

    def clear(self):
        if self.bits:
            ctypes.memset(self.bits, 0, self.width * self.height * 4)

    def update(self, hwnd, x, y, alpha=255):
        pt_dst = POINT(x, y)
        size = SIZE(self.width, self.height)
        pt_src = POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, alpha, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(hwnd, self.hdc_screen, ctypes.byref(pt_dst),
                                   ctypes.byref(size), self.hdc_mem, ctypes.byref(pt_src),
                                   0, ctypes.byref(blend), ULW_ALPHA)

    def release(self):
        if self.old_bitmap:
            gdi32.SelectObject(self.hdc_mem, self.old_bitmap)
            self.old_bitmap = None
        if self.hbitmap:
            gdi32.DeleteObject(self.hbitmap)
            self.hbitmap = None
        if self.hdc_mem:
            gdi32.DeleteDC(self.hdc_mem)
            self.hdc_mem = None
        if self.hdc_screen:
            user32.ReleaseDC(None, self.hdc_screen)
            self.hdc_screen = None
        self.bits = None
        self.width = self.height = 0


# ------------------------------------------------------------------ waveIn 录音
class WaveInRecorder:
    """基于 winmm waveIn 的 PCM 录音（16kHz/16bit/单声道）。

    无需窗口消息：使用 CALLBACK_NULL + 轮询缓冲状态。
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BITS = 16
    CHUNK_SECONDS = 0.5

    def __init__(self, max_seconds=60):
        self.max_seconds = max_seconds
        self._handle = wt.HANDLE()
        self._buffers = []
        self._headers = []
        self._opened = False
        self._recording = False

    def available(self):
        return winmm.waveInGetNumDevs() > 0

    def _fmt(self):
        f = WAVEFORMATEX()
        f.wFormatTag = WAVE_FORMAT_PCM
        f.nChannels = self.CHANNELS
        f.nSamplesPerSec = self.SAMPLE_RATE
        f.wBitsPerSample = self.BITS
        f.nBlockAlign = self.CHANNELS * self.BITS // 8
        f.nAvgBytesPerSec = self.SAMPLE_RATE * f.nBlockAlign
        f.cbSize = 0
        return f

    def open(self):
        if self._opened:
            return
        fmt = self._fmt()
        rc = winmm.waveInOpen(ctypes.byref(self._handle), WAVE_MAPPER, ctypes.byref(fmt),
                              None, None, CALLBACK_NULL)
        if rc != 0:
            raise RuntimeError('waveInOpen 失败，错误码 %d（麦克风可能被占用或未授权）' % rc)
        self._opened = True
        self._fmt_ref = fmt  # 保持引用，避免被回收

    def start(self):
        self.open()
        chunk = int(self.SAMPLE_RATE * self.CHUNK_SECONDS) * self.CHANNELS * (self.BITS // 8)
        # 全时长预排队：旧代码只有4个0.5秒缓冲，2秒后即停止收音。
        import math
        count = max(1, int(math.ceil(self.max_seconds / self.CHUNK_SECONDS)))
        for _ in range(count):
            buf = ctypes.create_string_buffer(chunk)
            hdr = WAVEHDR()
            hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
            hdr.dwBufferLength = chunk
            rc = winmm.waveInPrepareHeader(self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
            if rc != 0:
                winmm.waveInReset(self._handle)
                self._release_buffers()
                self.close()
                raise RuntimeError('录音缓冲准备失败，错误码 %d' % rc)
            self._buffers.append(buf)
            self._headers.append(hdr)
            rc = winmm.waveInAddBuffer(self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
            if rc != 0:
                winmm.waveInReset(self._handle)
                self._release_buffers()
                self.close()
                raise RuntimeError('录音缓冲排队失败，错误码 %d' % rc)
        rc = winmm.waveInStart(self._handle)
        if rc != 0:
            winmm.waveInReset(self._handle)
            self._release_buffers()
            self.close()
            raise RuntimeError('waveInStart 失败，错误码 %d' % rc)
        self._recording = True

    def stop(self):
        """停止录音并返回 PCM 数据（bytes）。"""
        if not self._recording:
            return b''
        self._recording = False
        winmm.waveInStop(self._handle)
        winmm.waveInReset(self._handle)
        data = bytearray()
        for buf, hdr in zip(self._buffers, self._headers):
            winmm.waveInUnprepareHeader(self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
            n = min(len(buf.raw), int(hdr.dwBytesRecorded or 0))
            data.extend(buf.raw[:n])
        self._buffers = []
        self._headers = []
        return bytes(data)

    def _release_buffers(self):
        for hdr in self._headers:
            winmm.waveInUnprepareHeader(self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        self._buffers = []
        self._headers = []

    def snapshot(self):
        """仅读取设备已填满的缓冲，不停止录音，也不重置设备。"""
        data = bytearray()
        for buf, hdr in list(zip(self._buffers, self._headers)):
            if hdr.dwFlags & 1:  # WHDR_DONE；当前正在写入的一块交给最终识别。
                data.extend(buf.raw[:min(len(buf.raw), int(hdr.dwBytesRecorded or 0))])
        return bytes(data)

    def close(self):
        if self._opened:
            try:
                winmm.waveInClose(self._handle)
            except Exception:
                pass
            self._opened = False

    @staticmethod
    def pcm_to_wav(pcm, sample_rate=SAMPLE_RATE, channels=CHANNELS, bits=BITS):
        """给 PCM 数据加 44 字节 WAV 头。"""
        import struct
        byte_rate = sample_rate * channels * bits // 8
        block_align = channels * bits // 8
        header = b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVE'
        header += b'fmt ' + struct.pack('<IHHIIHH', 16, 1, channels, sample_rate,
                                        byte_rate, block_align, bits)
        header += b'data' + struct.pack('<I', len(pcm))
        return header + pcm


# ------------------------------------------------------------------ MCI 播放
class MciPlayer:
    """用 MCI 播放本地音频文件（支持 mp3 / wav）。"""

    def __init__(self):
        self.alias = 'xiaoyin_tts'
        self.opened = False

    def play(self, path):
        self.stop()
        rc = winmm.mciSendStringW('open "%s" type mpegvideo alias %s' % (path, self.alias),
                                  None, 0, None)
        if rc != 0:
            rc = winmm.mciSendStringW('open "%s" alias %s' % (path, self.alias), None, 0, None)
        if rc != 0:
            raise RuntimeError('MCI 打开音频失败，错误码 %d' % rc)
        self.opened = True
        rc = winmm.mciSendStringW('play %s' % self.alias, None, 0, None)
        if rc != 0:
            self.stop()
            raise RuntimeError('MCI 播放失败，错误码 %d' % rc)

    def is_playing(self):
        if not self.opened:
            return False
        buf = ctypes.create_unicode_buffer(64)
        rc = winmm.mciSendStringW('status %s mode' % self.alias, buf, 64, None)
        if rc != 0:
            return False
        return buf.value.strip().lower() == 'playing'

    def stop(self):
        if self.opened:
            winmm.mciSendStringW('stop %s' % self.alias, None, 0, None)
            winmm.mciSendStringW('close %s' % self.alias, None, 0, None)
            self.opened = False
