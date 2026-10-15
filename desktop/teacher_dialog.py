# -*- coding: utf-8 -*-
"""原生教师对话框（Win32 HWND + 经典控件，非网页）。

支持（对应需求 5）：
- 教学环节切换（下拉框，来自 /api/knowledge/stages）
- 对话模式切换（教师课堂展示模式 / 学生探究模式）
- 文字对话（SSE 流式，逐字上屏）
- 语音对话（winmm waveIn 录音 → /api/asr；未配置时明确提示，不伪造）
- 停止生成（本地中断 + 通知后端）
- 播放控制（/api/tts → MCI 播放 / 停止播放）
- 收起面板（关闭对话框，悬浮头像收回）

线程模型：本窗口在其自己的线程上运行独立消息循环；网络与录音在 worker 线程执行，
结果通过线程安全队列 + WM_TIMER 回流到 UI 线程，避免跨线程操作控件。
"""
import ctypes
import os
import queue
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win32ui as W  # noqa: E402
from api_client import BackendClient, BackendError  # noqa: E402

CLASS_NAME = 'XiaoyinTeacherDialog'
WINDOW_TITLE = '森林小博士 · 教师端（原生桌面窗口）'

ID_STAGE = 2001
ID_MODE = 2002
ID_REFRESH = 2003
ID_TRANSCRIPT = 2004
ID_INPUT = 2005
ID_SEND = 2006
ID_STOP = 2007
ID_VOICE = 2008
ID_PLAY = 2009
ID_STOPPLAY = 2010
ID_CLEAR = 2011
ID_COLLAPSE = 2012
ID_STATUS = 2013
ID_CAP = 2014

EM_SETSEL = 0x00B1
EM_REPLACESEL = 0x00C2
EM_SCROLLCARET = 0x00B7
CB_ADDSTRING = 0x0143
CB_SETCURSEL = 0x014E
CB_GETCURSEL = 0x0147
CB_RESETCONTENT = 0x014B
VK_RETURN = 0x0D
VK_SHIFT = 0x10


def _dpi_scale():
    try:
        hdc = W.user32.GetDC(None)
        dpi = W.gdi32.GetDeviceCaps(hdc, 88)
        W.user32.ReleaseDC(None, hdc)
        return max(1.0, min(dpi / 96.0, 3.0))
    except Exception:
        return 1.0


class TeacherDialog:
    def __init__(self, base_url, on_close=None, state_setter=None, mode='teacher'):
        self.client = BackendClient(base_url)
        self.on_close = on_close or (lambda: None)
        self.state_setter = state_setter or (lambda s: None)
        self.initial_mode = mode

        self.hwnd = None
        self.hinstance = W.kernel32.GetModuleHandleW(None)
        self._wndproc_ref = None
        self._editproc_ref = None
        self._old_editproc = None
        self._brushes = {}
        self._fonts = {}
        self._queue = queue.Queue()
        self._lock = threading.RLock()

        self.scale = _dpi_scale()
        self.sid = ''
        self.stages = []
        self.stage_id = None
        self.mode = mode
        self.last_answer = ''
        self.cancel_flag = {'stop': False}
        self.recorder = None
        self.recording = False
        self.recorder_thread = None
        self.player = W.MciPlayer()
        self.temp_files = []
        self._busy = False
        self._closed = False
        self._voice_held = False
        self._voice_cancelled = False
        self._preview_pending = False

    # -------------------------------------------------- 尺寸助手
    def s(self, v):
        return int(round(v * self.scale))

    # -------------------------------------------------- 创建窗口
    def create(self):
        self._init_fonts()
        wc = W.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
        self._wndproc_ref = W.WNDPROC(self._wndproc)
        wc.lpfnWndProc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = self.hinstance
        wc.hCursor = W.user32.LoadCursorW(None, ctypes.c_wchar_p(W.IDC_ARROW))
        wc.hbrBackground = W.gdi32.CreateSolidBrush(W.rgb(251, 247, 236))
        wc.lpszClassName = CLASS_NAME
        if not W.user32.RegisterClassExW(ctypes.byref(wc)):
            err = W.kernel32.GetLastError()
            if err != 1410:
                raise RuntimeError('RegisterClassExW 失败，错误码 %d' % err)

        width, height = self.s(780), self.s(620)
        left, top, right, bottom = W.get_work_area()
        x = left + max(0, (right - left - width) // 2)
        y = top + max(0, (bottom - top - height) // 3)
        self.hwnd = W.user32.CreateWindowExW(
            0, CLASS_NAME, WINDOW_TITLE,
            W.WS_OVERLAPPEDWINDOW & ~W.WS_MAXIMIZEBOX,
            x, y, width, height, None, None, self.hinstance, None)
        if not self.hwnd:
            raise RuntimeError('CreateWindowExW 失败，错误码 %d' % W.kernel32.GetLastError())
        self._build_controls()
        W.user32.ShowWindow(self.hwnd, W.SW_SHOW)
        W.user32.UpdateWindow(self.hwnd)
        W.user32.SetTimer(self.hwnd, 2, 80, None)
        self._bootstrap()
        return self.hwnd

    def _init_fonts(self):
        self._fonts['ui'] = W.make_font(self.s(15))
        self._fonts['bold'] = W.make_font(self.s(15), bold=True)
        self._fonts['text'] = W.make_font(self.s(16))
        self._fonts['small'] = W.make_font(self.s(13))
        self._brushes['bg'] = W.gdi32.CreateSolidBrush(W.rgb(251, 247, 236))
        self._brushes['white'] = W.gdi32.CreateSolidBrush(W.rgb(255, 255, 255))

    def _mk(self, cls, text, style, x, y, w, h, cid, font='ui', extra_style=0):
        hwnd = W.user32.CreateWindowExW(
            extra_style, cls, text, W.WS_CHILD | W.WS_VISIBLE | style,
            self.s(x), self.s(y), self.s(w), self.s(h),
            self.hwnd, ctypes.c_void_p(cid), self.hinstance, None)
        if hwnd and font in self._fonts:
            W.user32.SendMessageW(hwnd, W.WM_SETFONT, self._fonts[font], 1)
        return hwnd

    def _build_controls(self):
        mk = self._mk
        mk('STATIC', '教学环节', W.SS_LEFT | W.SS_NOPREFIX, 14, 16, 62, 22, 0, 'bold')
        self.h_stage = mk('COMBOBOX', '', W.CBS_DROPDOWNLIST | W.CBS_HASSTRINGS, 78, 12, 300, 300, ID_STAGE)
        mk('STATIC', '模式', W.SS_LEFT | W.SS_NOPREFIX, 396, 16, 34, 22, 0, 'bold')
        self.h_mode = mk('COMBOBOX', '', W.CBS_DROPDOWNLIST | W.CBS_HASSTRINGS, 430, 12, 210, 300, ID_MODE)
        self.h_refresh = mk('BUTTON', '刷新状态', W.BS_PUSHBUTTON, 652, 11, 112, 28, ID_REFRESH)

        self.h_cap = mk('STATIC', '正在读取能力状态…', W.SS_LEFT | W.SS_NOPREFIX, 14, 44, 750, 44, ID_CAP, 'small')
        self.h_transcript = mk('EDIT', '', W.ES_MULTILINE | W.ES_READONLY | W.ES_AUTOVSCROLL
                               | W.WS_VSCROLL | W.ES_NOHIDESEL, 14, 92, 750, 366, ID_TRANSCRIPT, 'text')
        self.h_input = mk('EDIT', '', W.ES_MULTILINE | W.ES_AUTOVSCROLL | W.ES_WANTRETURN
                          | W.WS_VSCROLL, 14, 464, 750, 62, ID_INPUT, 'text')
        mk('STATIC', 'Enter 发送，Shift+Enter 换行', W.SS_LEFT | W.SS_NOPREFIX,
           14, 528, 260, 20, 0, 'small')

        bw, bh = 96, 32
        self.h_send = mk('BUTTON', '发送', W.BS_DEFPUSHBUTTON, 14, 552, bw, bh, ID_SEND)
        self.h_stop = mk('BUTTON', '停止生成', W.BS_PUSHBUTTON, 118, 552, bw, bh, ID_STOP)
        self.h_voice = mk('BUTTON', '语音对话', W.BS_PUSHBUTTON, 222, 552, bw, bh, ID_VOICE)
        self.h_play = mk('BUTTON', '播放回复', W.BS_PUSHBUTTON, 326, 552, bw, bh, ID_PLAY)
        self.h_stopplay = mk('BUTTON', '停止播放', W.BS_PUSHBUTTON, 430, 552, bw, bh, ID_STOPPLAY)
        self.h_clear = mk('BUTTON', '清空本会话', W.BS_PUSHBUTTON, 534, 552, 110, bh, ID_CLEAR)
        self.h_collapse = mk('BUTTON', '收起面板', W.BS_PUSHBUTTON, 652, 552, 112, bh, ID_COLLAPSE)

        self.h_status = mk('STATIC', '就绪', W.SS_LEFT | W.SS_NOPREFIX, 14, 590, 750, 22, ID_STATUS, 'small')

        self._subclass_input()
        W.user32.EnableWindow(self.h_stop, False)

    def _subclass_input(self):
        self._editproc_ref = W.WNDPROC(self._input_proc)
        self._old_editproc = W.user32.SetWindowLongPtrW(
            self.h_input, W.GWLP_WNDPROC, ctypes.cast(self._editproc_ref, ctypes.c_void_p))
        self._voiceproc_ref = W.WNDPROC(self._voice_proc)
        self._old_voiceproc = W.user32.SetWindowLongPtrW(
            self.h_voice, W.GWLP_WNDPROC, ctypes.cast(self._voiceproc_ref, ctypes.c_void_p))
        W.user32.SetWindowTextW(self.h_voice, '按住说话')

    def _voice_proc(self, hwnd, msg, wparam, lparam):
        down = msg == W.WM_LBUTTONDOWN or (msg == W.WM_KEYDOWN and wparam == 0x20)
        up = msg == W.WM_LBUTTONUP or (msg == 0x0101 and wparam == 0x20)
        if down:
            if not self._voice_held and not self._busy:
                self._voice_held = True
                self._voice_hold_at = time.monotonic()
                W.user32.SetCapture(hwnd)
                W.user32.SendMessageW(hwnd, 0x00F3, 1, 0)  # BM_SETSTATE
                self._on_voice()
            return 0
        if up or msg == 0x0215:  # WM_CAPTURECHANGED
            if self._voice_held:
                self._voice_held = False
                self._voice_cancelled = msg == 0x0215 or time.monotonic()-self._voice_hold_at < .35
                W.user32.ReleaseCapture()
                W.user32.SendMessageW(hwnd, 0x00F3, 0, 0)
                if self.recording:
                    self._stop_recording()
            return 0
        return W.user32.CallWindowProcW(self._old_voiceproc, hwnd, msg, wparam, lparam)

    def _input_proc(self, hwnd, msg, wparam, lparam):
        if msg == W.WM_KEYDOWN and wparam == VK_RETURN:
            shift = W.user32.GetKeyState(VK_SHIFT) & 0x8000
            if not shift:
                self._on_send()
                return 0
        return W.user32.CallWindowProcW(self._old_editproc, hwnd, msg, wparam, lparam)

    # -------------------------------------------------- 队列与 UI 更新
    def post(self, kind, payload=None):
        self._queue.put((kind, payload))

    def _drain_queue(self):
        for _ in range(200):
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._apply(kind, payload)
            except Exception as e:
                # 不再静默吞异常：写入 stderr（launcher 会收集到日志），便于排查
                sys.stderr.write('[对话框] 处理 %s 失败：%s: %s\n' % (kind, type(e).__name__, e))

    def _apply(self, kind, payload):
        if kind == 'log':
            self._append(payload)
        elif kind == 'delta':
            self._append(payload)
        elif kind == 'status':
            W.user32.SetWindowTextW(self.h_status, payload)
        elif kind == 'stages':
            W.user32.SendMessageW(self.h_stage, CB_RESETCONTENT, 0, 0)
            for st in payload:
                W.send_string(self.h_stage, CB_ADDSTRING, '%d. %s' % (st['order'], st['name']))
            if payload:
                W.user32.SendMessageW(self.h_stage, CB_SETCURSEL, 0, 0)
                self.stage_id = payload[0]['id']
        elif kind == 'caps':
            W.user32.SetWindowTextW(self.h_cap, payload)
        elif kind == 'busy':
            self._busy = bool(payload)
            W.user32.EnableWindow(self.h_send, not self._busy)
            W.user32.EnableWindow(self.h_stop, self._busy)
        elif kind == 'asr':
            W.user32.SetWindowTextW(self.h_input, payload)
            W.user32.SetFocus(self.h_input)
        elif kind == 'asr_preview':
            recorder, text = payload
            if self.recording and self.recorder is recorder:
                W.user32.SetWindowTextW(self.h_input, text)
        elif kind == 'voice_btn':
            W.user32.SetWindowTextW(self.h_voice, payload)
        elif kind == 'state':
            self.state_setter(payload)
        elif kind == 'session':
            self.sid = payload
        elif kind == 'clear':
            W.user32.SetWindowTextW(self.h_transcript, '')
        elif kind == 'input':
            W.user32.SetWindowTextW(self.h_input, payload)
        elif kind == 'collapse':
            self.close()

    def _append(self, text):
        length = W.user32.GetWindowTextLengthW(self.h_transcript)
        W.user32.SendMessageW(self.h_transcript, EM_SETSEL, length, length)
        W.send_string(self.h_transcript, EM_REPLACESEL, text)
        W.user32.SendMessageW(self.h_transcript, EM_SCROLLCARET, 0, 0)

    def _get_text(self, hwnd):
        n = W.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 2)
        W.user32.GetWindowTextW(hwnd, buf, n + 2)
        return buf.value

    # -------------------------------------------------- 启动引导
    def _bootstrap(self):
        threading.Thread(target=self._worker_bootstrap, daemon=True).start()

    def _worker_bootstrap(self):
        try:
            cfg = self.client.client_config()
            cap = cfg.get('capabilities', {})
            voice = cfg.get('voice', {})
            lines = []
            lines.append('大模型：%s（%s）' % (cap.get('llm', {}).get('label', '未知'),
                                          '真实 AI' if cap.get('llm', {}).get('state') == 'configured'
                                          else ('演示模式' if cap.get('llm', {}).get('state') == 'demo'
                                                else '未配置')))
            lines.append('图片分析：%s' % cap.get('vision', {}).get('label', ''))
            lines.append('语音识别 ASR：%s' % cap.get('asr', {}).get('label', ''))
            lines.append('语音合成 TTS：%s' % cap.get('tts', {}).get('label', ''))
            self.post('caps', '　|　'.join(lines))
            self.post('status', '就绪' if voice.get('chain_complete') else
                      '就绪（语音链路不完整：ASR 未配置，可用文字输入）')
        except BackendError as e:
            self.post('caps', '读取能力状态失败：%s' % e)
            self.post('status', '无法连接本地服务：%s' % e)
        try:
            stages = self.client.stages()
            self.stages = stages
            self.post('stages', stages)
        except BackendError as e:
            self.post('log', '[提示] 读取教学环节失败：%s\r\n' % e)
        try:
            sid = self.client.create_session(self.initial_mode)
            self.post('session', sid)
            self.post('log', '[系统] 教师会话已创建：%s（%s）\r\n' % (sid, self.initial_mode))
            self.post('log', '[系统] 密钥只保存在本地，界面不会显示密钥；未配置的能力会明确提示。\r\n\r\n')
        except BackendError as e:
            self.post('log', '[错误] 创建会话失败：%s\r\n' % e)
        # 模式下拉
        for label in ('教师课堂展示模式（可给完整解释）', '学生探究模式（先提示、只追问一个问题）'):
            W.send_string(self.h_mode, CB_ADDSTRING, label)
        W.user32.SendMessageW(self.h_mode, CB_SETCURSEL, 0, 0)
        self.mode = 'teacher'

    # -------------------------------------------------- 发送 / 停止
    def _on_send(self):
        if self._busy:
            return
        text = self._get_text(self.h_input).strip()
        if not text:
            return
        if not self.sid:
            self.post('log', '[提示] 会话尚未就绪，请稍候或点“刷新状态”。\r\n')
            return
        W.user32.SetWindowTextW(self.h_input, '')
        self._busy = True
        self._append('我：%s\r\n\r\n' % text)
        self.cancel_flag['stop'] = False
        self.post('busy', True)
        self.post('status', '思考中…')
        self.post('state', 'thinking')
        threading.Thread(target=self._worker_chat, args=(text,), daemon=True).start()

    def _worker_chat(self, text):
        acc = []

        def on_delta(piece):
            acc.append(piece)
            self.post('delta', piece)

        def on_event(ev):
            if ev.get('type') == 'error':
                self.post('log', '\r\n[错误] %s\r\n' % ev.get('message', ''))
            elif ev.get('type') == 'notice':
                self.post('log', '\r\n[提示] %s\r\n' % ev.get('message', ''))
            elif ev.get('type') == 'model':
                real = '真实 AI' if ev.get('is_real_ai') else '非真实 AI（演示模式）'
                self.post('log', '\r\n[模型] %s / %s · %s\r\n' % (ev.get('provider'), ev.get('model'), real))
            elif ev.get('type') == 'meta':
                ctx = ev.get('context') or {}
                self.post('log', '[上下文] 保留 %s 轮 / 共 %s 轮，估算 %s tokens（预算 %s）\r\n'
                          % (ctx.get('kept_turns'), ctx.get('total_turns'),
                             ctx.get('est_tokens'), ctx.get('token_budget')))
        try:
            answer, meta, error = self.client.chat_stream(
                self.sid, text, mode=self.mode, stage_id=self.stage_id,
                on_delta=on_delta, on_event=on_event,
                cancel_flag=lambda: self.cancel_flag['stop'])
            self.last_answer = answer or ''.join(acc)
            if self.cancel_flag['stop']:
                self.post('log', '\r\n[已停止生成]\r\n\r\n')
            elif not self.last_answer.strip():
                self.post('log', '\r\n[提示] 本次没有返回内容。\r\n\r\n')
            else:
                self.post('log', '\r\n\r\n')
        except BackendError as e:
            self.post('log', '\r\n[错误] %s\r\n\r\n' % e)
        finally:
            self.post('busy', False)
            self.post('status', '就绪')
            self.post('state', 'idle')

    def _on_stop(self):
        self.cancel_flag['stop'] = True
        self.post('status', '已请求停止生成…')
        if self.sid:
            try:
                self.client.stop_generation(self.sid)
            except BackendError:
                pass

    # -------------------------------------------------- 语音对话
    def _on_voice(self):
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._voice_cancelled = False
        if not self.recorder:
            self.recorder = W.WaveInRecorder(max_seconds=60)
        if not self.recorder.available():
            self.post('log', '\r\n[提示] 未检测到可用麦克风设备。\r\n')
            return
        try:
            self.recorder.start()
        except Exception as e:
            self.post('log', '\r\n[提示] 录音启动失败：%s\r\n' % e)
            return
        self.recording = True
        self.post('voice_btn', '松开结束')
        self.post('status', '正在听…松开结束，识别文字会逐步显示')
        self.post('state', 'listening')
        self.post('log', '\r\n[语音] 正在录音…\r\n')
        self.recorder_thread = threading.Thread(target=self._record_timer, daemon=True)
        self.recorder_thread.start()

    def _record_timer(self):
        """最长录音时间保护。"""
        limit = self.recorder.max_seconds
        recorder = self.recorder
        t0 = time.time()
        next_preview = t0 + 3
        while self.recording and self.recorder is recorder and time.time() - t0 < limit:
            time.sleep(0.2)
            if time.time() >= next_preview and not self._preview_pending:
                next_preview = time.time() + 3
                self._preview_pending = True
                threading.Thread(target=self._worker_asr_preview,args=(recorder,),daemon=True).start()
        if self.recording and self.recorder is recorder:
            self.post('log', '\r\n[语音] 达到最长录音时间，自动结束。\r\n')
            self._stop_recording()

    def _worker_asr_preview(self, recorder):
        try:
            pcm = recorder.snapshot()
            if not pcm or not self.recording or self.recorder is not recorder:
                return
            res = self.client.asr(W.WaveInRecorder.pcm_to_wav(pcm), audio_format='wav')
            if res.get('ok') and res.get('text'):
                self.post('asr_preview', (recorder, res['text']))
        except Exception:
            pass  # 预览失败不影响松开后的完整识别。
        finally:
            self._preview_pending = False

    def _stop_recording(self):
        self.recording = False
        self.post('voice_btn', '按住说话')
        self.post('state', 'thinking')
        self.post('status', '识别中…')
        threading.Thread(target=self._worker_asr, daemon=True).start()

    def _worker_asr(self):
        try:
            pcm = self.recorder.stop()
        except Exception as e:
            self.post('log', '\r\n[语音] 录音结束异常：%s\r\n' % e)
            pcm = b''
        finally:
            try:
                self.recorder.close()
            except Exception:
                pass
            self.recorder = None
        if self._voice_cancelled or len(pcm) < 11200:   # 误触或不足0.35秒
            self.post('log', '\r\n[语音] 没有录到声音，请再试一次。\r\n')
            self.post('status', '就绪')
            self.post('state', 'idle')
            return
        wav = W.WaveInRecorder.pcm_to_wav(pcm)
        try:
            res = self.client.asr(wav, audio_format='wav')
            if res.get('ok') and res.get('text'):
                self.post('asr', res['text'])
                self.post('log', '\r\n[语音识别] %s（已填入输入框，可修改后发送）\r\n' % res['text'])
            else:
                self.post('log', '\r\n[语音识别] 未返回文本。\r\n')
        except BackendError as e:
            if e.status == 501:
                miss = (e.payload or {}).get('missing_params') or []
                self.post('log', '\r\n[语音识别未配置] %s\r\n' % e)
                if miss:
                    self.post('log', '[缺少参数] %s\r\n' % '、'.join(miss))
                self.post('log', '[说明] 语音对话链路 = 录音 → 语音识别(ASR) → 模型 → 语音合成(TTS) → 播放；'
                                 'ASR 未配置时链路不完整，请先用文字输入。\r\n')
            else:
                self.post('log', '\r\n[语音识别失败] %s\r\n' % e)
        finally:
            self.post('status', '就绪')
            self.post('state', 'idle')

    # -------------------------------------------------- 播放控制
    def _on_play(self):
        text = (self.last_answer or '').strip()
        if not text:
            self.post('log', '\r\n[提示] 还没有可播放的回复。\r\n')
            return
        self.post('status', '正在合成语音…')
        self.post('state', 'speaking')
        threading.Thread(target=self._worker_tts, args=(text,), daemon=True).start()

    def _worker_tts(self, text):
        playback_version = getattr(self, '_audio_version', None)
        try:
            audio = self.client.tts(text[:300])
        except BackendError as e:
            if e.status == 501:
                miss = (e.payload or {}).get('missing_params') or []
                self.post('log', '\r\n[语音合成未配置] %s\r\n' % e)
                if miss:
                    self.post('log', '[缺少参数] %s\r\n' % '、'.join(miss))
                self.post('log', '[说明] 未配置时不会播放；浏览器端可退回系统朗读，桌面端暂以文字为主。\r\n')
            else:
                self.post('log', '\r\n[语音合成失败] %s\r\n' % e)
            self.post('status', '就绪')
            self.post('state', 'idle')
            return
        try:
            if playback_version != getattr(self, '_audio_version', None) or self._closed:
                return
            fd, path = tempfile.mkstemp(suffix='.mp3', prefix='xiaoyin_tts_')
            with os.fdopen(fd, 'wb') as f:
                f.write(audio)
            self.temp_files.append(path)
            self.player.play(path)
            self.post('playback_started', None)
            self.post('status', '播放中…（点“停止播放”可打断）')
        except Exception as e:
            self.post('log', '\r\n[播放失败] %s\r\n' % e)
            self.post('status', '就绪')
            self.post('state', 'idle')

    def _on_stop_play(self):
        try:
            self.player.stop()
        except Exception:
            pass
        self.post('status', '已停止播放')
        self.post('state', 'idle')

    # -------------------------------------------------- 其它
    def _on_clear(self):
        if not self.sid:
            return
        try:
            self.client.clear_session(self.sid)
            self.post('clear', None)
            self.post('log', '[系统] 本会话已清空。\r\n')
        except BackendError as e:
            self.post('log', '\r\n[提示] 清空失败：%s\r\n' % e)

    def _on_refresh(self):
        self.post('status', '正在刷新状态…')
        threading.Thread(target=self._worker_bootstrap, daemon=True).start()

    def close(self):
        self._closed = True
        try:
            if self.recording:
                self.recording = False
                if self.recorder:
                    try:
                        self.recorder.stop()
                        self.recorder.close()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            self.player.stop()
        except Exception:
            pass
        for p in list(self.temp_files):
            try:
                os.remove(p)
            except Exception:
                pass
        self.temp_files = []
        if self.hwnd:
            W.user32.DestroyWindow(self.hwnd)

    def bring_to_front(self):
        if self.hwnd:
            W.user32.ShowWindow(self.hwnd, W.SW_SHOW)
            W.set_foreground(self.hwnd)

    # -------------------------------------------------- 消息处理
    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == W.WM_COMMAND:
            cid = W.loword(wparam)
            code = W.hiword(wparam)
            if cid == ID_SEND and code == 0:
                self._on_send()
            elif cid == ID_STOP and code == 0:
                self._on_stop()
            elif cid == ID_VOICE and code == 0:
                pass  # 按下/松开由语音按钮子类处理，避免释放时再次启动。
            elif cid == ID_PLAY and code == 0:
                self._on_play()
            elif cid == ID_STOPPLAY and code == 0:
                self._on_stop_play()
            elif cid == ID_CLEAR and code == 0:
                self._on_clear()
            elif cid == ID_COLLAPSE and code == 0:
                self.close()
            elif cid == ID_REFRESH and code == 0:
                self._on_refresh()
            elif cid == ID_STAGE and code == 1:      # CBN_SELCHANGE
                idx = W.user32.SendMessageW(self.h_stage, CB_GETCURSEL, 0, 0)
                if 0 <= idx < len(self.stages):
                    self.stage_id = self.stages[idx]['id']
                    self.post('log', '[环节] 已切换到：%s\r\n' % self.stages[idx]['name'])
            elif cid == ID_MODE and code == 1:
                idx = W.user32.SendMessageW(self.h_mode, CB_GETCURSEL, 0, 0)
                self.mode = 'teacher' if idx == 0 else 'student'
                self.post('log', '[模式] 已切换到：%s\r\n'
                          % ('教师课堂展示模式' if self.mode == 'teacher' else '学生探究模式'))
            return 0
        if msg == W.WM_TIMER and wparam == 2:
            self._drain_queue()
            return 0
        if msg == W.WM_CTLCOLORSTATIC:
            hdc = wparam
            W.gdi32.SetBkMode(hdc, W.TRANSPARENT)
            W.gdi32.SetTextColor(hdc, W.rgb(28, 42, 30))
            return self._brushes['bg']
        if msg == W.WM_CTLCOLOREDIT:
            hdc = wparam
            W.gdi32.SetBkMode(hdc, W.TRANSPARENT)
            W.gdi32.SetTextColor(hdc, W.rgb(28, 42, 30))
            return self._brushes['white']
        if msg == W.WM_ERASEBKGND:
            return 1
        if msg == W.WM_CLOSE:
            self.close()
            return 0
        if msg == W.WM_DESTROY:
            W.user32.KillTimer(hwnd, 2)
            self.hwnd = None
            W.user32.PostQuitMessage(0)
            self.on_close()
            return 0
        return W.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self):
        return W.pump_messages()
