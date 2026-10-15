# -*- coding: utf-8 -*-
"""原生桌面悬浮窗（Win32 HWND，非网页元素）。

特性（对应需求 5）：
- 真正的原生桌面窗口：WS_EX_LAYERED 逐像素透明 + WS_EX_TOPMOST 置顶，
  在 PowerPoint / 希沃白板 / PDF 全屏放映时依然可见；
- 默认停在主显示器右下角（任务栏之上），可自由拖动，位置记忆在 data/desktop_ui.json；
- 左击（未拖动）→ 打开教师对话框；关闭对话框后头像自动收回（重新显示）；
- 右击 → 原生弹出菜单：打开对话框 / 置顶开关 / 重置位置 / 退出；
- 退出时由 launcher 负责释放自己启动的后端进程与服务；
- 头像按四状态（idle/listening/thinking/speaking）循环动画。
"""
import ctypes
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win32ui as W  # noqa: E402
import pngio  # noqa: E402

W.user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(W.POINT)]
W.user32.ValidateRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(W.RECT)]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVATAR_DIR = os.path.join(ROOT, 'assets', 'avatar')
UI_STATE = os.path.join(ROOT, 'data', 'desktop_ui.json')

CLASS_NAME = 'XiaoyinFloating'
WINDOW_TITLE = '森林小博士 · 悬浮伙伴'

IDM_OPEN = 1001
IDM_TOPMOST = 1002
IDM_RESET_POS = 1003
IDM_EXIT = 1004

STATES = ('idle', 'listening', 'thinking', 'speaking')
FRAME_SEQUENCE = {
    'idle': ('f0', 'f0', 'f2', 'f1', 'f0', 'f2'),           # 含眨眼
    'listening': ('f0', 'f1', 'f2', 'f1'),
    'thinking': ('f0', 'f1', 'f2', 'f1'),
    'speaking': ('f0', 'f1', 'f2', 'f1'),
}


def _dpi_scale():
    try:
        hdc = W.user32.GetDC(None)
        dpi = W.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        W.user32.ReleaseDC(None, hdc)
        return max(1.0, min(dpi / 96.0, 3.0))
    except Exception:
        return 1.0


def _load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return dict(default)


def _save_json(path, obj):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class FloatingWindow:
    """悬浮窗本体。"""

    def __init__(self, state_provider=None, on_open_dialog=None, on_exit=None,
                 on_state_change=None, activation_provider=None, on_activate=None):
        self.state_provider = state_provider or (lambda: 'idle')
        self.on_open_dialog = on_open_dialog or (lambda: None)
        self.on_exit = on_exit or (lambda: None)
        self.on_state_change = on_state_change or (lambda s: None)
        self.activation_provider = activation_provider or (lambda: False)
        self.on_activate = on_activate or self.show

        self.hwnd = None
        self.hinstance = W.kernel32.GetModuleHandleW(None)
        self._wndproc_ref = None
        self.canvas = W.LayeredCanvas()
        self.timer_id = 1
        self.frame_idx = 0
        self.cur_state = 'idle'
        self.frames = {}
        self.base_size = 0          # 头像原始尺寸
        self.display_size = 0       # 显示尺寸（物理像素）
        self.win_size = 0
        self._dragging = False
        self._drag_start = (0, 0)
        self._win_start = (0, 0)
        self._moved = False
        self._topmost = True
        self._pending_open = False
        self._ui = _load_json(UI_STATE, {'x': None, 'y': None, 'topmost': True})

    # -------------------------------------------------- 资源
    def load_frames(self):
        scale = _dpi_scale()
        self.display_size = int(round(72 * scale))
        self.win_size = self.display_size + int(round(24 * scale))   # 留出阴影/边距
        self.base_size = self.display_size
        for state in STATES:
            frames = []
            for suffix in ('f0', 'f1', 'f2'):
                p = os.path.join(AVATAR_DIR, 'forest-official.png')
                try:
                    w, h, rows = pngio.decode_png(p)
                    rows = self._circular_badge(rows, w, h)
                    frames.append(rows)
                except Exception:
                    frames.append(None)
            self.frames[state] = frames

    def _circular_badge(self, rows, width, height):
        """在原生分层窗口里绘制白色圆框，保留官方勘探家头像的透明边缘。"""
        size = self.display_size
        inner = int(size * 0.78)
        image = pngio.scale_rows(rows, width, height, inner, inner)
        inset = (size - inner) // 2
        center = (size - 1) / 2
        result = []
        for y in range(size):
            row = bytearray(size * 4)
            for x in range(size):
                distance = ((x-center)**2 + (y-center)**2)**0.5
                coverage = max(0.0, min(1.0, size/2-distance))
                if not coverage:
                    continue
                base = (232, 246, 251) if distance < size * 0.43 else (255, 255, 255)
                pixel = [*base, int(255*coverage)]
                ix, iy = x-inset, y-inset
                if 0 <= ix < inner and 0 <= iy < inner and distance < size * 0.43:
                    source = image[iy][ix*4:ix*4+4]
                    alpha = source[3]/255
                    pixel[:3] = [int(source[c]*alpha + base[c]*(1-alpha)) for c in range(3)]
                row[x*4:x*4+4] = bytes(pixel)
            result.append(bytes(row))
        return result

    # -------------------------------------------------- 窗口
    def create(self):
        self.load_frames()
        wc = W.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
        wc.style = 0
        self._wndproc_ref = W.WNDPROC(self._wndproc)
        wc.lpfnWndProc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = self.hinstance
        wc.hCursor = W.user32.LoadCursorW(None, ctypes.c_wchar_p(W.IDC_HAND))
        wc.hbrBackground = None
        wc.lpszClassName = CLASS_NAME
        wc.lpszMenuName = None
        if not W.user32.RegisterClassExW(ctypes.byref(wc)):
            err = W.kernel32.GetLastError()
            if err != 1410:  # 类已注册
                raise RuntimeError('RegisterClassExW 失败，错误码 %d' % err)

        x, y = self._initial_pos()
        ex_style = W.WS_EX_LAYERED | W.WS_EX_TOOLWINDOW
        if self._ui.get('topmost', True):
            ex_style |= W.WS_EX_TOPMOST
        self._topmost = bool(self._ui.get('topmost', True))
        self.hwnd = W.user32.CreateWindowExW(
            ex_style, CLASS_NAME, WINDOW_TITLE, W.WS_POPUP,
            x, y, self.win_size, self.win_size, None, None, self.hinstance, None)
        if not self.hwnd:
            raise RuntimeError('CreateWindowExW 失败，错误码 %d' % W.kernel32.GetLastError())
        self.canvas.ensure(self.win_size, self.win_size)
        self._render()
        W.user32.ShowWindow(self.hwnd, W.SW_SHOWNOACTIVATE)
        W.user32.SetTimer(self.hwnd, self.timer_id, 260, None)
        return self.hwnd

    def _initial_pos(self):
        left, top, right, bottom = W.get_work_area()
        margin = int(round(16 * _dpi_scale()))
        x = self._ui.get('x')
        y = self._ui.get('y')
        if x is None or y is None or not (left - 200 <= x <= right + 200):
            x = right - self.win_size - margin
            y = bottom - self.win_size - margin
        return int(x), int(y)

    def _render(self):
        state = self.cur_state
        seq = FRAME_SEQUENCE.get(state, ('f0',))
        suffix = seq[self.frame_idx % len(seq)]
        idx = {'f0': 0, 'f1': 1, 'f2': 2}.get(suffix, 0)
        frame = None
        frames = self.frames.get(state) or []
        if frames:
            frame = frames[idx] or frames[0]
        if frame is None:
            return
        self.canvas.clear()
        pad = (self.win_size - self.display_size) // 2
        self.canvas.blit_rgba(frame, pad, pad)
        x, y = W.window_rect(self.hwnd)[:2]
        self.canvas.update(self.hwnd, x, y)

    # -------------------------------------------------- 消息
    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == W.WM_LBUTTONDOWN:
            self._dragging = True
            self._moved = False
            point = W.POINT(W.get_x_lparam(lparam), W.get_y_lparam(lparam))
            W.user32.ClientToScreen(hwnd, ctypes.byref(point))
            self._drag_start = (point.x, point.y)
            self._win_start = W.window_rect(hwnd)[:2]
            W.user32.SetCapture(hwnd)
            return 0
        if msg == W.WM_MOUSEMOVE:
            if self._dragging:
                # 客户区原点随窗口移动，不能用它和按下时的局部坐标相减。
                # 每次先转换为屏幕坐标，避免窗口追着自身坐标反复跳回。
                point = W.POINT(W.get_x_lparam(lparam), W.get_y_lparam(lparam))
                W.user32.ClientToScreen(hwnd, ctypes.byref(point))
                dx = point.x - self._drag_start[0]
                dy = point.y - self._drag_start[1]
                if abs(dx) > 4 or abs(dy) > 4:
                    self._moved = True
                if self._moved:
                    nx = self._win_start[0] + dx
                    ny = self._win_start[1] + dy
                    # 分层窗口的现有像素会随 SetWindowPos 移动，无需再上传位图。
                    W.user32.SetWindowPos(hwnd, None, nx, ny, 0, 0,
                                          W.SWP_NOSIZE | W.SWP_NOZORDER | W.SWP_NOACTIVATE)
            return 0
        if msg == W.WM_LBUTTONUP:
            if not self._dragging:
                return 0
            self._dragging = False
            W.user32.ReleaseCapture()
            if not self._moved:
                # 左击 → 打开对话框
                self._save_pos()
                self.on_open_dialog()
            else:
                self._save_pos()
            return 0
        if msg == W.WM_RBUTTONUP:
            self._show_menu()
            return 0
        if msg in (0x0215, 0x001F):  # WM_CAPTURECHANGED / WM_CANCELMODE
            if self._dragging:
                self._dragging = False
                self._save_pos()
            return 0
        if msg == W.WM_TIMER:
            if getattr(self, 'activation_provider', lambda: False)():
                self.on_activate()
            # 拖动时保持当前头像帧，避免移动与动画反复上传同一分层位图。
            if self._dragging:
                return 0
            self.frame_idx += 1
            state = self.state_provider() or 'idle'
            if state != self.cur_state and state in self.frames:
                self.cur_state = state
                self.frame_idx = 0
                self.on_state_change(state)
            self._render()
            return 0
        if msg == W.WM_COMMAND:
            self._on_menu(W.loword(wparam))
            return 0
        if msg == W.WM_ERASEBKGND:
            return 1
        if msg == W.WM_PAINT:
            # 分层位图由 UpdateLayeredWindow 管理，确认更新区域避免空转重绘。
            W.user32.ValidateRect(hwnd, None)
            return 0
        if msg == W.WM_DESTROY:
            W.user32.KillTimer(hwnd, self.timer_id)
            self._save_pos()
            W.user32.PostQuitMessage(0)
            return 0
        if msg == W.WM_CLOSE:
            W.user32.DestroyWindow(hwnd)
            return 0
        return W.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_menu(self):
        menu = W.user32.CreatePopupMenu()
        W.user32.AppendMenuW(menu, W.MF_STRING, IDM_OPEN, '打开对话框')
        W.user32.AppendMenuW(menu, W.MF_SEPARATOR, 0, None)
        flags = W.MF_STRING | (W.MF_CHECKED if self._topmost else 0)
        W.user32.AppendMenuW(menu, flags, IDM_TOPMOST, '总在最前（置顶）')
        W.user32.AppendMenuW(menu, W.MF_STRING, IDM_RESET_POS, '回到右下角')
        W.user32.AppendMenuW(menu, W.MF_SEPARATOR, 0, None)
        W.user32.AppendMenuW(menu, W.MF_STRING, IDM_EXIT, '退出森林小博士')
        x, y = W.window_rect(self.hwnd)[:2]
        W.user32.SetForegroundWindow(self.hwnd)
        cmd = W.user32.TrackPopupMenu(menu, W.TPM_RETURNCMD | W.TPM_RIGHTBUTTON,
                                      x + 20, y + 20, 0, self.hwnd, None)
        W.user32.DestroyMenu(menu)
        if cmd:
            self._on_menu(cmd)

    def _on_menu(self, cmd):
        if cmd == IDM_OPEN:
            self.on_open_dialog()
        elif cmd == IDM_TOPMOST:
            self._topmost = not self._topmost
            W.user32.SetWindowPos(self.hwnd, W.HWND_TOPMOST if self._topmost else W.HWND_NOTOPMOST,
                                  0, 0, 0, 0, W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)
            self._ui['topmost'] = self._topmost
            _save_json(UI_STATE, self._ui)
        elif cmd == IDM_RESET_POS:
            left, top, right, bottom = W.get_work_area()
            margin = int(round(16 * _dpi_scale()))
            nx = right - self.win_size - margin
            ny = bottom - self.win_size - margin
            W.user32.SetWindowPos(self.hwnd, None, nx, ny, 0, 0,
                                  W.SWP_NOSIZE | W.SWP_NOZORDER | W.SWP_NOACTIVATE)
            self._save_pos()
        elif cmd == IDM_EXIT:
            self.request_exit()

    def _save_pos(self):
        if not self.hwnd:
            return
        x, y = W.window_rect(self.hwnd)[:2]
        self._ui['x'] = int(x)
        self._ui['y'] = int(y)
        _save_json(UI_STATE, self._ui)

    # -------------------------------------------------- 对外接口
    def set_state(self, state):
        if state in self.frames:
            self.cur_state = state
            self.frame_idx = 0

    def show(self):
        if self.hwnd:
            W.user32.ShowWindow(self.hwnd, W.SW_SHOWNOACTIVATE)
            W.user32.SetWindowPos(self.hwnd, W.HWND_TOPMOST if self._topmost else W.HWND_NOTOPMOST,
                                  0, 0, 0, 0, W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)

    def hide(self):
        if self.hwnd:
            W.user32.ShowWindow(self.hwnd, W.SW_HIDE)

    def request_exit(self):
        """退出：销毁窗口 → 消息循环结束 → launcher 负责释放子进程。"""
        self._save_pos()
        if self.hwnd:
            W.user32.DestroyWindow(self.hwnd)

    def run(self):
        code = W.pump_messages()
        self.canvas.release()
        self.on_exit()
        return code
