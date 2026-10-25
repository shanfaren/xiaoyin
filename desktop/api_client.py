# -*- coding: utf-8 -*-
"""后端 HTTP 客户端（供桌面端使用）。

要点：
- 显式禁用系统代理（ProxyHandler({})），保证 127.0.0.1 请求在设置了系统代理的机器上依然可用；
- 支持 SSE 流式对话、停止生成、ASR、TTS；
- 所有网络错误转为可读的中文提示，不吞掉原因。
"""
import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE = 'http://127.0.0.1:8000'
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class BackendError(Exception):
    def __init__(self, message, status=None, payload=None):
        self.status = status
        self.payload = payload
        super().__init__(message)


class BackendClient:
    def __init__(self, base_url=DEFAULT_BASE, timeout=20):
        self.base = (base_url or DEFAULT_BASE).rstrip('/')
        self.timeout = timeout

    # ------------------------------------------------ 基础请求
    def _request(self, method, path, body=None, timeout=None, raw=False):
        url = self.base + path
        data = None
        headers = {'Accept': 'application/json'}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            resp = _opener.open(req, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as e:
            payload = None
            try:
                payload = json.loads(e.read().decode('utf-8', 'ignore'))
            except Exception:
                payload = None
            msg = (payload or {}).get('message') or ('HTTP %s' % e.code)
            raise BackendError(msg, status=e.code, payload=payload)
        except Exception as e:
            raise BackendError('无法连接本地服务（%s）：%s' % (self.base, e))
        with resp:
            data_bytes = resp.read()
        if raw:
            return resp.status, data_bytes
        try:
            return resp.status, json.loads(data_bytes.decode('utf-8'))
        except Exception:
            return resp.status, data_bytes

    # ------------------------------------------------ 接口
    def health(self):
        return self._request('GET', '/api/health')[1]

    def client_config(self):
        return self._request('GET', '/api/client-config')[1]

    def stages(self):
        return self._request('GET', '/api/knowledge/stages')[1].get('stages', [])

    def create_session(self, mode='teacher'):
        _, j = self._request('POST', '/api/session', {'mode': mode})
        return j.get('session_id', '')

    def get_session(self, sid):
        _, j = self._request('GET', '/api/session/%s' % sid)
        return j.get('session', {})

    def clear_session(self, sid):
        return self._request('POST', '/api/session/%s/clear' % sid)[1]

    def stop_generation(self, sid):
        return self._request('POST', '/api/chat/stop', {'session_id': sid})[1]

    def suggestions(self, sid, stage_id):
        return self._request('POST', '/api/session/%s/suggestions' % sid,
                             {'stage_id': stage_id}, timeout=30)[1].get('questions', [])

    def asr(self, wav_bytes, audio_format='wav'):
        import base64
        body = {'audio_base64': base64.b64encode(wav_bytes).decode('ascii'), 'format': audio_format}
        return self._request('POST', '/api/asr', body, timeout=60)[1]

    def tts(self, text, voice=None):
        body = {'text': text}
        if voice:
            body['voice'] = voice
        status, data = self._request('POST', '/api/tts', body, timeout=60, raw=True)
        return data

    # ------------------------------------------------ SSE 流式对话
    def chat_stream(self, sid, text, mode='teacher', stage_id=None,
                    on_event=None, on_delta=None, cancel_flag=None):
        """流式对话。返回 (完整回答, meta, 错误信息或 None)。
        cancel_flag: 可调用对象，返回 True 时主动中断读取（本地停止）。
        """
        body = {'session_id': sid, 'text': text, 'mode': mode}
        if stage_id:
            body['stage_id'] = stage_id
        req = urllib.request.Request(
            self.base + '/api/chat',
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream'},
            method='POST')
        answer_parts = []
        meta = {}
        error = None
        try:
            resp = _opener.open(req, timeout=120)
        except Exception as e:
            raise BackendError('对话请求失败：%s' % e)
        with resp:
            buf = b''
            while True:
                if cancel_flag and cancel_flag():
                    break
                chunk = resp.read(1)
                if not chunk:
                    break
                buf += chunk
                if buf.endswith(b'\n\n'):
                    for line in buf.decode('utf-8', 'ignore').split('\n'):
                        if not line.startswith('data: '):
                            continue
                        try:
                            ev = json.loads(line[6:])
                        except Exception:
                            continue
                        if ev.get('type') == 'delta':
                            answer_parts.append(ev.get('text', ''))
                            if on_delta:
                                on_delta(ev.get('text', ''))
                        elif ev.get('type') == 'meta':
                            meta = ev
                            if on_event:
                                on_event(ev)
                        elif ev.get('type') == 'model':
                            meta['model_info'] = ev
                            if on_event:
                                on_event(ev)
                        elif ev.get('type') == 'error':
                            error = ev
                            if on_event:
                                on_event(ev)
                        elif ev.get('type') in ('notice', 'done'):
                            if on_event:
                                on_event(ev)
                    buf = b''
        return ''.join(answer_parts), meta, error
