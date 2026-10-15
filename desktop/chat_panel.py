# -*- coding: utf-8 -*-
"""截图参考的原生圆角聊天面板，复用教师端网络和音频功能。"""
import ctypes
import ctypes.wintypes as wt
import threading

import win32ui as W
import teacher_dialog as T
from bubble_transcript import BubbleTranscript

ID_PIN = 2101
ID_MORE = 2102
PROFILE_IDS = ('qa', 'hint', 'share')


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [('hdc', wt.HDC), ('erase', wt.BOOL), ('rect', W.RECT),
                ('restore', wt.BOOL), ('inc', wt.BOOL), ('reserved', ctypes.c_byte * 32)]


class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [('type', wt.UINT), ('id', wt.UINT), ('item', wt.UINT), ('action', wt.UINT),
                ('state', wt.UINT), ('hwnd', wt.HWND), ('hdc', wt.HDC),
                ('rect', W.RECT), ('data', ctypes.c_size_t)]


W.user32.BeginPaint.argtypes = [wt.HWND, ctypes.c_void_p]
W.user32.BeginPaint.restype = wt.HDC
W.user32.EndPaint.argtypes = [wt.HWND, ctypes.c_void_p]
W.user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(W.RECT), wt.HBRUSH]
W.user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(W.RECT), wt.UINT]
W.user32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
W.user32.DrawFocusRect.argtypes = [wt.HDC, ctypes.POINTER(W.RECT)]
W.gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
W.gdi32.CreateRoundRectRgn.restype = wt.HANDLE
W.gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.COLORREF]
W.gdi32.CreatePen.restype = wt.HANDLE
W.gdi32.RoundRect.argtypes = [wt.HDC] + [ctypes.c_int] * 6


class ChatPanel(T.TeacherDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pinned = True
        self.more = False
        self.settings = []
        self.panel_w = 460
        self.panel_h = 660
        self._labels = {}
        self._destroyed = threading.Event()
        self.stage_id = 'qa'
        self.profile_buttons = []
        self.profiles = []
        self.suggestion_buttons = []
        self.suggested_questions = []
        self._suggestion_version = 0
        self.chat_view = None
        self._audio_version = 0
        self._playback_started = False
        self._asr_pending = False

    def close(self):
        # launcher 在悬浮头像线程调用退出，销毁必须回到面板所属线程。
        if self.hwnd:
            W.user32.PostMessageW(self.hwnd, W.WM_APP + 32, 0, 0)
            self._destroyed.wait(2)

    def create(self):
        left, top, right, bottom = W.get_work_area()
        self.scale = min(self.scale, (right-left-24)/460, (bottom-top-24)/660)
        self._init_fonts()
        self._fonts['suggestion'] = W.make_font(self.s(12))
        self._fonts['title'] = W.make_font(self.s(17), bold=True)
        wc = W.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(wc)
        self._wndproc_ref = W.WNDPROC(self._wndproc)
        wc.lpfnWndProc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = self.hinstance
        wc.hCursor = W.user32.LoadCursorW(None, ctypes.c_wchar_p(W.IDC_ARROW))
        wc.hbrBackground = self._brushes['white']
        wc.lpszClassName = T.CLASS_NAME
        if not W.user32.RegisterClassExW(ctypes.byref(wc)) and W.kernel32.GetLastError() != 1410:
            raise ctypes.WinError(ctypes.get_last_error())
        left, top, right, bottom = W.get_work_area()
        # 小屏幕上保持整个面板可见。
        width, height = self.s(self.panel_w), self.s(self.panel_h)
        self.hwnd = W.user32.CreateWindowExW(
            W.WS_EX_TOPMOST | W.WS_EX_APPWINDOW, T.CLASS_NAME, '森林小博士 · 电脑本地版',
            W.WS_POPUP | W.WS_CLIPCHILDREN, right-width-self.s(16),
            bottom-height-self.s(16), width, height, None, None, self.hinstance, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        region = W.gdi32.CreateRoundRectRgn(0, 0, width+1, height+1, self.s(32), self.s(32))
        if not W.user32.SetWindowRgn(self.hwnd, region, True):
            W.gdi32.DeleteObject(region)
        self._build_controls()
        W.user32.ShowWindow(self.hwnd, W.SW_SHOW)
        W.user32.UpdateWindow(self.hwnd)
        W.user32.SetTimer(self.hwnd, 2, 80, None)
        self._bootstrap()
        W.user32.SetFocus(self.h_input)
        return self.hwnd

    def _init_fonts(self):
        super()._init_fonts()
        W.gdi32.DeleteObject(self._brushes['bg'])
        self._brushes['bg'] = W.gdi32.CreateSolidBrush(W.rgb(255, 250, 243))

    def _button(self, label, x, y, width, cid, height=34):
        self._labels[cid] = label
        button = self._mk('BUTTON', label, 0xB | W.WS_TABSTOP,
                          x, y, width, height, cid)
        region = W.gdi32.CreateRoundRectRgn(0, 0, self.s(width)+1, self.s(height)+1,
                                           self.s(12), self.s(12))
        if not W.user32.SetWindowRgn(button, region, True):
            W.gdi32.DeleteObject(region)
        return button

    def _build_controls(self):
        mk = self._mk
        self.h_collapse = self._button('−', 16, 15, 34, T.ID_COLLAPSE)
        self.h_pin = self._button('置顶', 56, 15, 48, ID_PIN)
        self._button('···', 406, 15, 36, ID_MORE)
        self.h_play = self._button('朗读', 346, 15, 52, T.ID_PLAY)
        for i, label in enumerate(('提问答疑', '探究提示', '收获分享')):
            self.profile_buttons.append(self._button(label, 28+i*138, 77, 128, 2201+i))
        self.h_transcript = mk('EDIT', '', W.ES_MULTILINE | W.ES_READONLY |
                              W.ES_AUTOVSCROLL,
                              28, 126, 404, 358, T.ID_TRANSCRIPT, 'text')
        W.user32.ShowWindow(self.h_transcript, W.SW_HIDE)
        self.chat_view = BubbleTranscript(self.hwnd,self.scale,self._fonts['text'],self._fonts['small'])
        self.chat_view.create(28,126,404,358)
        self.h_reco_label = mk('STATIC','接下来还可以问',W.SS_NOPREFIX,28,420,300,14,0,'suggestion')
        W.user32.ShowWindow(self.h_reco_label,W.SW_HIDE)
        for i in range(2):
            button = self._button('', 28, 436+i*26, 404, 2301+i, 22)
            self.suggestion_buttons.append(button)
            W.user32.ShowWindow(button, W.SW_HIDE)
        self.h_input = mk('EDIT', '', W.ES_MULTILINE | W.ES_AUTOVSCROLL |
                         W.ES_WANTRETURN | W.WS_TABSTOP,
                         38, 518, 382, 52, T.ID_INPUT, 'text')
        # 原生编辑框的占位文字，不影响中文输入法。
        W.send_string(self.h_input, 0x1501, '发消息，和森林小博士一起探索…', 1)
        self._button('对话', 34, 582, 54, ID_MORE)
        self.h_clear = self._button('新对话', 96, 582, 66, T.ID_CLEAR)
        self.h_stop = self._button('停止', 218, 582, 48, T.ID_STOP)
        self.h_voice = self._button('语音对话', 274, 582, 76, T.ID_VOICE)
        self.h_send = self._button('发送 ↑', 358, 582, 72, T.ID_SEND)
        self.h_status = mk('STATIC', '正在连接…', W.SS_NOPREFIX, 28, 633, 404, 18,
                           T.ID_STATUS, 'small')
        self.h_stage = mk('COMBOBOX', '', W.CBS_DROPDOWNLIST | W.CBS_HASSTRINGS,
                          28, 88, 404, 240, T.ID_STAGE)
        self.h_mode = mk('COMBOBOX', '', W.CBS_DROPDOWNLIST | W.CBS_HASSTRINGS,
                         28, 134, 404, 240, T.ID_MODE)
        self.h_cap = mk('STATIC', '正在读取能力状态…', W.SS_NOPREFIX,
                        28, 180, 404, 90, T.ID_CAP, 'small')
        self.h_refresh = self._button('刷新状态', 28, 278, 96, T.ID_REFRESH)
        self.h_stopplay = self._button('停止朗读', 140, 278, 96, T.ID_STOPPLAY)
        self.settings = [self.h_mode, self.h_cap, self.h_refresh, self.h_stopplay]
        for hwnd in self.settings + [self.h_stage]:
            W.user32.ShowWindow(hwnd, W.SW_HIDE)
        self._subclass_input()
        W.user32.EnableWindow(self.h_stop, False)

    def _round(self, hdc, rect, color, radius=18, border=None):
        brush = W.gdi32.CreateSolidBrush(W.rgb(*color))
        pen = W.gdi32.CreatePen(0, 1, W.rgb(*(border or color)))
        old_b = W.gdi32.SelectObject(hdc, brush)
        old_p = W.gdi32.SelectObject(hdc, pen)
        W.gdi32.RoundRect(hdc, *rect, self.s(radius), self.s(radius))
        W.gdi32.SelectObject(hdc, old_b)
        W.gdi32.SelectObject(hdc, old_p)
        W.gdi32.DeleteObject(brush)
        W.gdi32.DeleteObject(pen)

    def _text(self, hdc, text, rect, font='ui', color=(34, 36, 39), flags=0x24):
        old = W.gdi32.SelectObject(hdc, self._fonts[font])
        W.gdi32.SetBkMode(hdc, W.TRANSPARENT)
        W.gdi32.SetTextColor(hdc, W.rgb(*color))
        r = W.RECT(*rect)
        W.user32.DrawTextW(hdc, text, -1, ctypes.byref(r), flags)
        W.gdi32.SelectObject(hdc, old)

    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = W.user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            r = W.RECT(0, 0, self.s(460), self.s(660))
            W.user32.FillRect(hdc, ctypes.byref(r), self._brushes['bg'])
            self._text(hdc, '森林小博士', tuple(self.s(v) for v in (122, 15, 338, 49)), 'title')
            line = W.RECT(0, self.s(64), self.s(460), self.s(65))
            brush = W.gdi32.CreateSolidBrush(W.rgb(241, 241, 243))
            W.user32.FillRect(hdc, ctypes.byref(line), brush)
            W.gdi32.DeleteObject(brush)
            self._round(hdc, tuple(self.s(v) for v in (19, 499, 441, 625)),
                        (255, 255, 255), 48, (228, 229, 232))
        finally:
            W.user32.EndPaint(hwnd, ctypes.byref(ps))

    def _draw_button(self, lp):
        item = ctypes.cast(lp, ctypes.POINTER(DRAWITEMSTRUCT)).contents
        cid = item.id
        text = self._get_text(item.hwnd)
        selected = bool(item.state & 1)
        active = (cid == T.ID_SEND or (cid == ID_PIN and self.pinned) or
                  (2201 <= cid <= 2203 and PROFILE_IDS[cid-2201] == self.stage_id))
        color = (231, 241, 231) if active else (249, 241, 229)
        if selected:
            color = (221, 232, 225)
        r = item.rect
        # 先清除系统按钮底色，否则圆弧外会残留灰色方角。
        W.user32.FillRect(item.hdc, ctypes.byref(r), self._brushes['bg'])
        self._round(item.hdc, (r.left+1, r.top+1, r.right-1, r.bottom-1), color, 12)
        disabled = bool(item.state & 4)
        font = 'suggestion' if 2301 <= cid <= 2302 else 'ui'
        self._text(item.hdc, text, (r.left, r.top, r.right, r.bottom),
                   font=font, color=(170, 172, 176) if disabled else (34, 36, 39), flags=0x25)
        if item.state & 16:  # 使用同形圆角焦点边框，保留键盘操作提示。
            self._round(item.hdc, (r.left+1, r.top+1, r.right-1, r.bottom-1),
                        color, 12, (121, 151, 134))
            self._text(item.hdc, text, (r.left, r.top, r.right, r.bottom),
                       font=font, color=(34, 36, 39), flags=0x25)
        return 1

    def _apply(self, kind, payload):
        if kind == 'suggestions':
            version, selected, questions = payload
            if version != self._suggestion_version or selected != self.stage_id or self._busy or self.more:
                return
            self.suggested_questions = questions[:2]
            W.user32.SetWindowPos(self.chat_view.hwnd, None, self.s(28), self.s(126),
                                  self.s(404), self.s(292 if questions else 358), W.SWP_NOZORDER)
            W.user32.ShowWindow(self.h_reco_label,W.SW_SHOW if questions else W.SW_HIDE)
            for i, button in enumerate(self.suggestion_buttons):
                if i < len(self.suggested_questions):
                    W.user32.SetWindowTextW(button, self.suggested_questions[i])
                    W.user32.ShowWindow(button, W.SW_SHOW)
                else:
                    W.user32.ShowWindow(button, W.SW_HIDE)
        elif kind == 'stages':
            self.profiles = payload
            self.stages = payload
            self._profile_hint()
        elif kind == 'asr':
            self._asr_pending = False
            self._apply('busy',False)
            W.user32.SetWindowTextW(self.h_input, payload)
            self._on_send()
        elif kind == 'autoplay':
            version, answer = payload
            if version == self._audio_version and not self._busy:
                self.last_answer = answer
                self._on_play()
        elif kind == 'clear':
            self.chat_view.clear()
            super()._apply(kind,payload)
        elif kind == 'playback_started':
            self._playback_started = True
        elif kind == 'modes':
            W.user32.SendMessageW(self.h_mode, T.CB_RESETCONTENT, 0, 0)
            for label in ('教师课堂展示', '学生自主探究'):
                W.send_string(self.h_mode, T.CB_ADDSTRING, label)
            W.user32.SendMessageW(self.h_mode, T.CB_SETCURSEL,
                                  0 if self.mode == 'teacher' else 1, 0)
        else:
            if kind == 'status' and payload == '就绪' and self._asr_pending:
                self._asr_pending = False
                self._apply('busy',False)
            super()._apply(kind, payload)
        if kind == 'busy':
            for button in self.profile_buttons:
                W.user32.EnableWindow(button, not payload)
            W.user32.EnableWindow(self.h_voice,not payload)
            W.user32.EnableWindow(self.h_clear,not payload)
            W.user32.EnableWindow(self.h_play,not payload)

    def _profile_hint(self):
        selected = next((p for p in self.profiles if p['id'] == self.stage_id), None)
        if selected:
            W.send_string(self.h_input, 0x1501, selected.get('placeholder', selected['goal']), 1)
            W.user32.SetWindowTextW(self.h_status, selected['goal'])
        for button in self.profile_buttons:
            W.user32.InvalidateRect(button, None, True)

    def _hide_suggestions(self):
        self._suggestion_version += 1
        self.suggested_questions = []
        W.user32.ShowWindow(self.h_reco_label,W.SW_HIDE)
        for button in self.suggestion_buttons:
            W.user32.ShowWindow(button, W.SW_HIDE)
        W.user32.SetWindowPos(self.chat_view.hwnd, None, self.s(28), self.s(126),
                              self.s(404), self.s(358), W.SWP_NOZORDER)

    def _on_send(self):
        if self.recording:
            return
        if not self._busy and self._get_text(self.h_input).strip() and self.sid:
            self._audio_version += 1
            self._playback_started = False
            self.player.stop()
            self._hide_suggestions()
        super()._on_send()

    def _worker_chat(self, text):
        version, selected = self._suggestion_version, self.stage_id
        audio_version = self._audio_version
        self.last_answer = ''
        super()._worker_chat(text)
        if self.last_answer and not self.cancel_flag['stop']:
            self.post('autoplay', (audio_version,self.last_answer))
            try:
                questions = self.client.suggestions(self.sid, selected)
                self.post('suggestions', (version, selected, questions))
            except T.BackendError:
                pass

    def _on_clear(self):
        self._audio_version += 1
        self._playback_started = False
        self.player.stop()
        self._hide_suggestions()
        super()._on_clear()

    def _append(self,text):
        super()._append(text)
        if self.chat_view:
            self.chat_view.append(text)

    def _on_voice(self):
        if self._busy:
            return
        self._audio_version += 1
        self._playback_started = False
        self.player.stop()
        super()._on_voice()

    def _stop_recording(self):
        with self._lock:
            if self._asr_pending:
                return
            self._asr_pending = True
        self._busy=True
        self.post('busy',True)
        super()._stop_recording()

    def _on_play(self):
        self._audio_version += 1
        self._playback_started = False
        self.player.stop()
        super()._on_play()

    def _on_stop_play(self):
        self._audio_version += 1
        self._playback_started = False
        super()._on_stop_play()

    def _worker_bootstrap(self):
        # 网络工作线程仅投递消息，不直接操作控件。
        try:
            cfg = self.client.client_config()
            cap = cfg.get('capabilities', {})
            self.post('caps', '\r\n'.join('%s：%s' % (label, cap.get(key, {}).get('label', '未配置'))
                      for key, label in [('llm', '对话'), ('vision', '图片'), ('asr', '语音识别'), ('tts', '朗读')]))
            demo = cap.get('llm', {}).get('state') == 'demo'
            self.post('status', '演示模式 · 非真实 AI' if demo else 'Enter 发送 · Shift+Enter 换行')
            self.stages = self.client.stages()
            self.post('stages', self.stages)
            if not self.sid:
                self.post('session', self.client.create_session(self.initial_mode))
                self.post('log', '你好，我是森林小博士。\r\n和我一起寻找大自然里的隐身高手吧！\r\n\r\n')
        except T.BackendError as e:
            self.post('status', '连接失败，请在“···”中刷新状态')
            self.post('log', '[提示] %s\r\n' % e)
        self.post('modes')

    def post(self, kind, payload=None):
        if kind == 'log' and payload and payload.startswith(('\r\n[语音识别]', '\r\n[语音] 正在录音')):
            return
        # 调试信息留给日志，聊天区只展示面向课堂的内容。
        if kind == 'log' and payload and payload.startswith(('[上下文]', '\r\n[模型]')):
            if '非真实 AI' in payload:
                super().post('log', '（演示模式 · 非真实 AI）\r\n')
            return
        super().post(kind, payload)

    def _wndproc(self, hwnd, msg, wp, lp):
        if msg == W.WM_TIMER and self._playback_started and not self.player.is_playing():
            self._playback_started = False
            self.player.stop()
            self.state_setter('idle')
            self._profile_hint()
        if msg == W.WM_APP + 32:
            self.cancel_flag['stop'] = True
            super().close()
            return 0
        if msg == W.WM_DESTROY:
            result = super()._wndproc(hwnd, msg, wp, lp)
            self._destroyed.set()
            return result
        if msg == W.WM_CLOSE or (msg == W.WM_COMMAND and W.loword(wp) == T.ID_COLLAPSE):
            # 收起保留当前会话和原生控件，再点头像继续刚才的对话。
            W.user32.ShowWindow(hwnd, W.SW_HIDE)
            self.on_close()
            return 0
        if msg == W.WM_PAINT:
            self._paint(hwnd)
            return 0
        if msg == W.WM_MOUSEWHEEL and self.chat_view:
            return self.chat_view._wndproc(self.chat_view.hwnd,msg,wp,lp)
        if msg == 0x2B:  # WM_DRAWITEM
            return self._draw_button(lp)
        if msg == W.WM_LBUTTONDOWN and W.get_y_lparam(lp) < self.s(64):
            W.user32.ReleaseCapture()
            W.user32.SendMessageW(hwnd, 0xA1, W.HTCAPTION, lp)
            return 0
        if msg == W.WM_COMMAND and W.hiword(wp) == 0:
            cid = W.loword(wp)
            if 2301 <= cid <= 2303:
                index = cid-2301
                if not self._busy and index < len(self.suggested_questions):
                    W.user32.SetWindowTextW(self.h_input, self.suggested_questions[index])
                    self._on_send()
                return 0
            if 2201 <= cid <= 2203:
                if not self._busy:
                    self._hide_suggestions()
                    self.stage_id = PROFILE_IDS[cid-2201]
                    if self.more:
                        self.more = False
                        W.user32.ShowWindow(self.chat_view.hwnd, W.SW_SHOW)
                        for control in self.settings:
                            W.user32.ShowWindow(control, W.SW_HIDE)
                    self._profile_hint()
                return 0
            if cid == ID_PIN:
                self.pinned = not self.pinned
                W.user32.SetWindowPos(hwnd, W.HWND_TOPMOST if self.pinned else W.HWND_NOTOPMOST,
                                      0, 0, 0, 0, W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)
                W.user32.InvalidateRect(self.h_pin, None, True)
                return 0
            if cid == ID_MORE:
                self._hide_suggestions()
                self.more = not self.more
                W.user32.ShowWindow(self.chat_view.hwnd, W.SW_HIDE if self.more else W.SW_SHOW)
                for control in self.settings:
                    W.user32.ShowWindow(control, W.SW_SHOW if self.more else W.SW_HIDE)
                W.user32.InvalidateRect(hwnd, None, True)
                return 0
        if msg == W.WM_CTLCOLORSTATIC and lp == self.h_transcript:
            W.gdi32.SetBkColor(wp, W.rgb(255, 255, 255))
            W.gdi32.SetTextColor(wp, W.rgb(34, 36, 39))
            return self._brushes['white']
        return super()._wndproc(hwnd, msg, wp, lp)
