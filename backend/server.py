# -*- coding: utf-8 -*-
"""课程智能体后端服务（纯标准库实现，无第三方依赖）。

启动：python -m backend.server            （默认 0.0.0.0:8000）
      python -m backend.server --port 8000

路由一览
--------
页面
  GET  /                     学生端（手机/平板，移动优先）
  GET  /scan                 扫码入口单页（适合插入 PPT）
  GET  /teacher              教师对话面板
  GET  /static/*             前端静态资源
  GET  /assets/*             角色头像等资源

公开接口（学生端可用）
  GET  /api/health           健康检查
  GET  /api/client-config    客户端安全配置（不含任何密钥）
  POST /api/session          创建会话 {mode}
  GET  /api/session/<id>     读取会话（刷新后恢复）
  POST /api/session/<id>/clear   清空本会话
  POST /api/session/<id>/stage   切换教学环节
  POST /api/chat             SSE 流式对话
  POST /api/chat/stop        停止生成
  POST /api/asr              语音识别（未配置时明确返回 501 + 缺失参数）
  POST /api/tts              语音合成（同上）
  POST /api/vision           图片分析（同上）

管理接口（仅回环地址，或携带 X-Admin-Token；用于教师 PC 本地管理）
  GET  /api/admin/capabilities   能力与缺失参数报告
  GET  /api/admin/network        局域网地址、候选二维码地址、连通自检
  GET  /api/admin/config         读取配置（密钥掩码）
  POST /api/admin/config         更新配置（密钥只写入本地 config/config.json）
  GET  /api/admin/qrcode.png     生成二维码 PNG（带往返校验）
  GET  /api/admin/qrcode.svg     生成二维码 SVG
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 允许 `python backend/server.py` 直接运行
if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'backend'

from backend import config as cfgmod            # noqa: E402
from backend import netutil                     # noqa: E402
from backend import qr_encode, qr_image         # noqa: E402
from backend.adapters.asr import ASRClient      # noqa: E402
from backend.adapters.errors import NotConfigured, RateLimited, UpstreamError  # noqa: E402
from backend.adapters.llm import LLMClient, summarize  # noqa: E402
from backend.adapters.tts import TTSClient      # noqa: E402
from backend.adapters.vision import VisionClient  # noqa: E402
from backend.knowledge import demo_responder, prompts  # noqa: E402
from backend.knowledge import interactions
from backend.knowledge import followups
from backend.session import RateLimiter, SessionStore  # noqa: E402

VERSION = '1.0.0'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(PROJECT_ROOT, 'web')
ASSETS_DIR = os.path.join(PROJECT_ROOT, 'assets')
MAX_BODY = 12 * 1024 * 1024   # 12MB（含 base64 后的图片/音频）


class AppState:
    def __init__(self):
        self.cfg = cfgmod.load_config()
        self.store = SessionStore(ttl_hours=self.cfg['limits']['session_ttl_hours'])
        self.limiter = RateLimiter()
        self.cancels = {}
        self.cancel_lock = threading.RLock()
        self.started_at = time.time()
        self.suggestion_cache = {}
        self._build_clients()

    def _build_clients(self):
        self.llm = LLMClient(self.cfg, demo_responder=lambda msgs: demo_responder.respond(
            msgs, mode='student', stage_id=None))
        self.vision = VisionClient(self.cfg)
        self.asr = ASRClient(self.cfg)
        self.tts = TTSClient(self.cfg)

    def reload(self):
        self.cfg = cfgmod.load_config()
        self._build_clients()

    # ---- 取消生成 ----
    def set_cancel(self, sid, flag=True):
        with self.cancel_lock:
            self.cancels[sid] = flag

    def is_cancelled(self, sid):
        with self.cancel_lock:
            return bool(self.cancels.get(sid))

    def clear_cancel(self, sid):
        with self.cancel_lock:
            self.cancels.pop(sid, None)


STATE = AppState()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'XiaoyinAgent/' + VERSION

    # ---------------- 基础工具 ----------------
    def log_message(self, fmt, *args):
        try:
            msg = cfgmod.redact(fmt % args)
        except Exception:
            msg = 'log'
        sys.stderr.write('[%s] %s\n' % (time.strftime('%H:%M:%S'), msg))

    def _client_ip(self):
        if STATE.cfg['server'].get('trust_proxy_headers'):
            fwd = self.headers.get('X-Forwarded-For')
            if fwd:
                return fwd.split(',')[0].strip()
        return self.client_address[0]

    def _public_origin(self):
        """从代理/请求头识别公网来源，形如 https://xxxx.onrender.com。
        云端（Render）据此让二维码自动指向公网域名，无需手填 public_base_url。"""
        if not STATE.cfg['server'].get('trust_proxy_headers'):
            return ''
        host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host') or ''
        host = host.split(',')[0].strip()
        if not host:
            return ''
        proto = (self.headers.get('X-Forwarded-Proto') or '').split(',')[0].strip() or 'https'
        return f'{proto}://{host}'

    def _admin_allowed(self):
        tok = str(STATE.cfg['server'].get('admin_token') or '').strip()
        if netutil.is_loopback(self._client_ip()):
            return True
        if tok and self.headers.get('X-Admin-Token') == tok:
            return True
        return False

    def _send_json(self, obj, status=200, extra_headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        # Close JSON responses so unread rejected request bodies cannot corrupt
        # the next request on a proxy's reused HTTP/1.1 connection.
        self.send_header('Connection', 'close')
        self.close_connection = True
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data, ctype, status=200, filename=None, cache=False):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Cache-Control', 'public, max-age=3600' if cache else 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError(f'请求体过大（{length} 字节 > 上限 {MAX_BODY}）')
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception as e:
            raise ValueError(f'JSON 解析失败：{e}')

    # ---------------- SSE ----------------
    def _sse_start(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-transform')
        self.send_header('X-Accel-Buffering', 'no')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

    def _sse_send(self, obj):
        payload = ('data: ' + json.dumps(obj, ensure_ascii=False) + '\n\n').encode('utf-8')
        self.wfile.write(('%X\r\n' % len(payload)).encode('ascii') + payload + b'\r\n')
        self.wfile.flush()

    def _sse_end(self):
        try:
            self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()
        except Exception:
            pass

    # ---------------- 路由 ----------------
    def do_GET(self):
        try:
            self._route_get()
        except Exception as e:
            self._safe_error(e)

    def do_POST(self):
        try:
            self._route_post()
        except Exception as e:
            self._safe_error(e)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _cors(self):
        origins = STATE.cfg['server'].get('allow_cors_origins') or []
        origin = self.headers.get('Origin')
        if origins and origin and origin in origins:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type,X-Admin-Token')

    def _safe_error(self, e):
        try:
            self.log_message('ERROR %s\n%s', e, traceback.format_exc()[:1200])
            if isinstance(e, ValueError):
                self._send_json({'ok': False, 'error': 'bad_request', 'message': str(e)}, 400)
            else:
                self._send_json({'ok': False, 'error': 'internal', 'message': str(e)}, 500)
        except Exception:
            pass

    # ============ GET ============
    def _route_get(self):
        path = self.path.split('?')[0]
        query = {}
        if '?' in self.path:
            for kv in self.path.split('?', 1)[1].split('&'):
                if '=' in kv:
                    k, v = kv.split('=', 1)
                    query[k] = v

        if path in ('/', '/index.html'):
            return self._serve_file(os.path.join(WEB_DIR, 'index.html'))
        if path in ('/scan', '/scan.html'):
            return self._serve_file(os.path.join(WEB_DIR, 'scan.html'))
        if path in ('/teacher', '/teacher.html'):
            return self._serve_file(os.path.join(WEB_DIR, 'teacher.html'))
        if path.startswith('/static/'):
            return self._serve_static(WEB_DIR, path[len('/static/'):])
        if path.startswith('/assets/'):
            return self._serve_static(ASSETS_DIR, path[len('/assets/'):])

        if path == '/api/health':
            return self._send_json({
                'ok': True, 'service': 'xiaoyin-course-agent', 'version': VERSION,
                'uptime_seconds': int(time.time() - STATE.started_at),
                'capabilities': cfgmod.capability_report(STATE.cfg),
                'sessions_in_memory': len(STATE.store._cache),
            })
        if path == '/api/client-config':
            return self._send_json(self._client_config())
        if path == '/api/knowledge/stages':
            return self._send_json({'ok': True, 'stages': prompts.stage_list()})
        if path == '/api/access-info':
            return self._send_json(self._access_info())
        if path == '/api/qrcode.png':
            # 公开接口：二维码内容即学生需要访问的地址，本身不是敏感信息
            return self._qrcode_png(query, admin=False)
        if path == '/api/qrcode.svg':
            return self._qrcode_svg(query, admin=False)
        if path.startswith('/api/session/'):
            parts = path[len('/api/session/'):].split('/')
            sid = parts[0]
            mode = query.get('mode')
            if len(parts) == 1:
                s = STATE.store.get(sid, mode=mode)
                if not s:
                    return self._send_json({'ok': False, 'error': 'not_found',
                                            'message': '会话不存在或已超过恢复期限'}, 404)
                return self._send_json({'ok': True, 'session': s.to_dict()})
        if path == '/api/admin/capabilities':
            return self._admin(lambda: self._send_json(self._capabilities()))
        if path == '/api/admin/network':
            return self._admin(lambda: self._send_json(self._network_info()))
        if path == '/api/admin/config':
            return self._admin(lambda: self._send_json(self._config_masked()))
        if path == '/api/admin/qrcode.png':
            return self._admin(lambda: self._qrcode_png(query))
        if path == '/api/admin/qrcode.svg':
            return self._admin(lambda: self._qrcode_svg(query))

        return self._send_json({'ok': False, 'error': 'not_found', 'path': path}, 404)

    # ============ POST ============
    def _route_post(self):
        path = self.path.split('?')[0]
        if path == '/api/session':
            body = self._read_json()
            mode = body.get('mode') or 'student'
            if mode not in ('student', 'teacher'):
                raise ValueError('mode 只能为 student 或 teacher')
            selected = interactions.resolve_id(body.get('stage_id'))
            s = STATE.store.create(mode)
            s.stage_id = selected
            STATE.store.persist(s)
            return self._send_json({'ok': True, 'session_id': s.id, 'mode': s.mode,
                                    'session': s.to_dict()})
        if path.startswith('/api/session/'):
            parts = path[len('/api/session/'):].split('/')
            sid = parts[0]
            s = STATE.store.get(sid)
            if not s:
                return self._send_json({'ok': False, 'error': 'not_found'}, 404)
            if len(parts) == 2 and parts[1] == 'clear':
                STATE.store.clear(s)
                return self._send_json({'ok': True, 'message': '本会话已清空', 'session': s.to_dict()})
            if len(parts) == 2 and parts[1] == 'stage':
                body = self._read_json()
                s.stage_id = interactions.resolve_id(body.get('stage_id'))
                STATE.store.persist(s)
                return self._send_json({'ok': True, 'stage_id': s.stage_id})
            if len(parts) == 2 and parts[1] == 'suggestions':
                return self._suggestions(s)
        if path == '/api/chat':
            return self._chat()
        if path == '/api/chat/stop':
            body = self._read_json()
            sid = body.get('session_id')
            STATE.set_cancel(sid, True)
            return self._send_json({'ok': True, 'message': '已请求停止生成', 'session_id': sid})
        if path == '/api/asr':
            return self._asr()
        if path == '/api/tts':
            return self._tts()
        if path == '/api/vision':
            return self._vision()
        if path == '/api/admin/config':
            return self._admin(self._update_config)
        return self._send_json({'ok': False, 'error': 'not_found', 'path': path}, 404)

    def _suggestions(self, session):
        body = self._read_json()
        selected = interactions.resolve_id(body.get('stage_id') or session.stage_id)
        with session.lock:
            latest = session.messages[-2:]
            if len(latest) != 2 or latest[0]['role'] != 'user' or latest[1]['role'] != 'assistant':
                return self._send_json({'ok': True, 'questions': []})
            question, answer = latest[0]['content'], latest[1]['content']
            turn = latest[1]['turn']
        key = (session.id, selected, question, answer)
        cached = STATE.suggestion_cache.get(key)
        if cached is not None:
            return self._send_json({'ok': True, 'questions': cached, 'stage_id': selected, 'turn': turn})
        allowed, _ = STATE.limiter.allow('suggestions:' + session.id, 20)
        if not allowed:
            return self._send_json({'ok': False, 'questions': [], 'error': 'rate_limited'}, 429)
        if not STATE.llm.is_ready() or STATE.llm.is_demo():
            return self._send_json({'ok': True, 'questions': [], 'note': '推荐问题需要真实模型'})
        try:
            stream, _ = STATE.llm.generate(followups.messages_for(selected, question, answer))
            items = followups.parse_questions(''.join(stream), question)
            if len(STATE.suggestion_cache) >= 128:
                STATE.suggestion_cache.pop(next(iter(STATE.suggestion_cache)), None)
            STATE.suggestion_cache[key] = items
            return self._send_json({'ok': True, 'questions': items, 'stage_id': selected, 'turn': turn})
        except Exception as exc:
            return self._send_json({'ok': False, 'questions': [], 'error': 'suggestions_unavailable',
                                    'message': cfgmod.redact(str(exc))}, 502)

    def _admin(self, fn):
        if not self._admin_allowed():
            return self._send_json({'ok': False, 'error': 'forbidden',
                                    'message': '管理接口仅允许从本机（127.0.0.1）访问，或提供正确的 X-Admin-Token'}, 403)
        return fn()

    # ---------------- 静态文件 ----------------
    def _serve_static(self, base, rel):
        rel = rel.split('?')[0].lstrip('/')
        if '..' in rel or rel.startswith('/'):
            return self._send_json({'ok': False, 'error': 'bad_path'}, 400)
        return self._serve_file(os.path.join(base, rel))

    def _serve_file(self, full):
        if not os.path.isfile(full):
            return self._send_json({'ok': False, 'error': 'not_found', 'file': os.path.basename(full)}, 404)
        ctype, _ = mimetypes.guess_type(full)
        ctype = ctype or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json'):
            ctype += '; charset=utf-8'
        with open(full, 'rb') as f:
            data = f.read()
        cache = not full.endswith('.html')
        if ctype.startswith('video/'):
            return self._send_video(data, ctype)
        return self._send_bytes(data, ctype, cache=cache)

    def _send_video(self, data, ctype):
        """Single byte-range support for mobile browsers and looping playback."""
        size = len(data)
        start, end, status = 0, size - 1, 200
        requested = self.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested.strip())
            try:
                if not match or not any(match.groups()):
                    raise ValueError()
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), size - 1) if right else size - 1
                else:
                    length = int(right)
                    if length <= 0:
                        raise ValueError()
                    start = max(0, size - length)
                if start >= size or start > end:
                    raise ValueError()
                status = 206
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%d' % size)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Cache-Control', 'public, max-age=3600')
        if status == 206:
            self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        self.end_headers()
        self.wfile.write(data[start:end + 1])

    # ---------------- 配置 ----------------
    def _client_config(self):
        cfg = STATE.cfg
        cap = cfgmod.capability_report(cfg)
        base = cfg['server'].get('public_base_url') or ''
        ip = netutil.primary_ip()
        return {
            'ok': True,
            'character': {'name': cfg['character']['name'], 'alias': cfg['character'].get('alias', ''),
                          'welcome': cfg['character']['welcome']},
            'course': {'name': cfg['character']['course_name'], 'stage_grade': '幼儿园大班', 'subject': '科学'},
            'stages': prompts.stage_list(),
            'quick_questions': prompts.KB['student_quick_questions'],
            'limits': {'max_input_chars': cfg['limits']['max_input_chars'],
                       'max_image_mb': cfg['limits']['max_image_mb']},
            'capabilities': cap,
            'voice': {
                'asr': cap['asr'], 'tts': cap['tts'],
                'browser_fallback': cap['browser_speech_fallback'],
                'chain': ['录音', '语音识别(ASR)', '模型理解', '语音合成(TTS)', '播放'],
                'chain_complete': cap['asr']['state'] == 'configured' and cap['llm']['state'] == 'configured',
                'text_only_fallback': True,
                'auto_send': True,
                'auto_play': True,
            },
            'vision': cap['vision'],
            'lan_hint': {'primary_ip': ip, 'port': cfg['server']['port'],
                         'public_base_url': base},
            'demo': {'enabled': cap['llm']['demo_mode'], 'label': cfg['modes']['demo_label']},
        }

    def _capabilities(self):
        cap = cfgmod.capability_report(STATE.cfg)
        return {
            'ok': True, 'capabilities': cap,
            'asr_detail': STATE.asr.status(),
            'tts_detail': STATE.tts.status(),
            'vision_ready': STATE.vision.is_ready(),
            'llm_ready': STATE.llm.is_ready(),
            'demo_mode': STATE.llm.is_demo(),
            'config_path': cfgmod.CONFIG_PATH,
            'config_exists': os.path.isfile(cfgmod.CONFIG_PATH),
        }

    def _network_info(self):
        cfg = STATE.cfg
        port = cfg['server']['port']
        base = cfg['server'].get('public_base_url') or ''
        cands = netutil.candidate_urls(port, base)
        for c in cands:
            c['check'] = netutil.check_url(c['url'])
        recommended = None
        for c in cands:
            if c['kind'] == 'public':
                recommended = c
                break
        if not recommended:
            for c in cands:
                if c['kind'] == 'lan' and c['check'].get('reachable'):
                    recommended = c
                    break
        return {
            'ok': True,
            'primary_ip': netutil.primary_ip(),
            'all_ipv4': netutil.all_ipv4(),
            'port': port,
            'candidates': cands,
            'recommended': recommended,
            'notes': [
                '学生二维码必须指向实际可达的地址；禁止使用 127.0.0.1 / localhost。',
                '同 Wi-Fi 局域网模式：手机与本机须在同一网段；若路由器开启「AP 隔离/客户端隔离」或使用校园网，设备间可能互相不可达。',
                '公网模式：需将本服务部署到公网服务器并配置 HTTPS 域名，二维码指向该 HTTPS 地址。',
                '如需修改 Windows 防火墙放行端口，请由用户自行决定与操作，本程序不会修改任何系统安全/防火墙设置。',
            ],
        }

    def _access_info(self):
        cfg = STATE.cfg
        port = cfg['server']['port']
        base = cfg['server'].get('public_base_url') or self._public_origin()
        cands = netutil.candidate_urls(port, base)
        lan = [c for c in cands if c['kind'] == 'lan']
        pub = [c for c in cands if c['kind'] == 'public']
        recommended = (pub[0] if pub else (lan[0] if lan else None))
        return {
            'ok': True,
            'mode': 'public' if pub else 'lan',
            'recommended_url': recommended['url'] if recommended else '',
            'recommended_kind': recommended['kind'] if recommended else '',
            'public_base_url': base,
            'lan_urls': [c['url'] for c in lan],
            'primary_ip': netutil.primary_ip(),
            'port': port,
            'character': {'name': cfg['character']['name']},
            'notes': [
                '同 Wi-Fi 局域网模式：手机与本机需在同一网段。',
                '部分路由器开启「AP 隔离/客户端隔离」，或使用校园网（跨网段/需认证）时，手机可能无法访问本机。',
                '公网模式：需部署到公网服务器并配置 HTTPS 域名，二维码指向该地址。',
            ],
        }

    def _config_masked(self):
        cfg = json.loads(json.dumps(STATE.cfg, ensure_ascii=False))

        def mask(d, key='api_key'):
            if isinstance(d, dict) and d.get(key):
                v = str(d[key])
                d[key] = ('****' + v[-4:]) if len(v) > 4 else '****'
        for path in (('llm', 'primary'), ('llm', 'fallback'), ('vision',), ('asr',), ('tts',)):
            node = cfg
            for p in path:
                node = node.get(p, {}) if isinstance(node, dict) else {}
            mask(node)
        return {'ok': True, 'config': cfg, 'config_path': cfgmod.CONFIG_PATH,
                'note': '密钥以掩码显示，不会通过接口返回明文；明文只保存在本地 config/config.json 或环境变量中。'}

    def _update_config(self):
        body = self._read_json()
        patch = body.get('patch') or {}
        if not isinstance(patch, dict):
            raise ValueError('patch 必须是对象')

        def merge(base, over):
            for k, v in over.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    merge(base[k], v)
                else:
                    base[k] = v
        cur = STATE.cfg
        merge(cur, patch)
        cfgmod.save_config(cur)
        STATE.reload()
        return self._send_json({'ok': True, 'message': '配置已保存到本地并重新加载（密钥仅存于本机）',
                                'capabilities': cfgmod.capability_report(STATE.cfg)})

    # ---------------- 二维码 ----------------
    def _qrcode_target(self, query):
        if query.get('url'):
            target = query['url']
        else:
            base = STATE.cfg['server'].get('public_base_url') or self._public_origin()
            if base:
                target = base.rstrip('/') + '/scan'
            else:
                target = f"http://{netutil.primary_ip()}:{STATE.cfg['server']['port']}/scan"
        low = target.lower()
        if 'localhost' in low or '127.0.0.1' in low:
            raise ValueError('禁止将 localhost/127.0.0.1 编码进二维码：学生手机无法访问该地址')
        return target

    def _qrcode_png(self, query, admin=True):
        target = self._qrcode_target(query)
        scale = int(query.get('scale', 10))
        data, meta = qr_image.render_png_bytes(target, scale=max(4, min(scale, 20)))
        meta['target_url'] = target
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-QR-Target', target)
        self.send_header('X-QR-Version', str(meta['version']))
        self.send_header('X-QR-Roundtrip', 'ok' if meta.get('roundtrip_verified') else 'failed')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _qrcode_svg(self, query, admin=True):
        target = self._qrcode_target(query)
        matrix, version, mask = qr_encode.make_matrix(target)
        ok, detail = qr_encode.verify(matrix, target)
        n = len(matrix)
        border = 4
        scale = 8
        size = (n + border * 2) * scale
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
                 f'viewBox="0 0 {n + border * 2} {n + border * 2}" shape-rendering="crispEdges">',
                 f'<rect width="{n + border * 2}" height="{n + border * 2}" fill="#ffffff"/>',
                 '<path fill="#111111" d="']
        for r in range(n):
            c = 0
            while c < n:
                if matrix[r][c]:
                    start = c
                    while c < n and matrix[r][c]:
                        c += 1
                    parts.append(f'M{start + border} {r + border}h{c - start}v1h-{c - start}z')
                else:
                    c += 1
        parts.append('"/></svg>')
        svg = ''.join(parts).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'image/svg+xml; charset=utf-8')
        self.send_header('Content-Length', str(len(svg)))
        self.send_header('X-QR-Target', target)
        self.send_header('X-QR-Roundtrip', 'ok' if ok else 'failed')
        self.end_headers()
        self.wfile.write(svg)

    # ---------------- 对话（SSE） ----------------
    def _chat(self):
        body = self._read_json()
        sid = body.get('session_id')
        text = (body.get('text') or '').strip()
        mode = body.get('mode') or 'student'
        if mode not in ('student', 'teacher'):
            raise ValueError('mode 只能为 student 或 teacher')
        s = STATE.store.get(sid, mode=mode)
        if not s:
            self._sse_start()
            self._sse_send({'type': 'error', 'code': 'session_not_found',
                            'message': '会话不存在或已过期，请重新开始'})
            return self._sse_end()
        if not text:
            self._sse_start()
            self._sse_send({'type': 'error', 'code': 'empty_input', 'message': '请输入内容'})
            return self._sse_end()

        max_chars = int(STATE.cfg['limits']['max_input_chars'])
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        else:
            truncated = False

        # 限流
        ok_s, n_s = STATE.limiter.allow('s:' + sid, int(STATE.cfg['limits']['rate_per_minute_per_session']))
        if not ok_s:
            self._sse_start()
            self._sse_send({'type': 'error', 'code': 'rate_limited',
                            'message': f'提问太快啦，请等一会儿再问（每分钟上限 {STATE.cfg["limits"]["rate_per_minute_per_session"]} 次）'})
            return self._sse_end()
        ok_g, _ = STATE.limiter.allow('global', int(STATE.cfg['limits']['rate_per_minute_global']))
        if not ok_g:
            self._sse_start()
            self._sse_send({'type': 'error', 'code': 'rate_limited_global',
                            'message': '当前使用人数较多，请稍后再试'})
            return self._sse_end()

        s.stage_id = interactions.resolve_id(body.get('stage_id') or s.stage_id)

        # 上下文（保证最近 ≥min_keep_turns 轮完整进入模型）
        def _summarizer(old_text):
            return summarize(STATE.llm, old_text)
        history, ctx_meta = s.build_context(
            max_history_turns=int(STATE.cfg['limits']['max_history_turns']),
            min_keep_turns=int(STATE.cfg['limits']['min_keep_turns']),
            token_budget=int(STATE.cfg['limits']['context_token_budget']),
            summarizer=_summarizer if STATE.llm.is_ready() else None,
        )

        system_prompt = prompts.build_system_prompt(
            character_name=STATE.cfg['character']['name'], mode=mode,
            stage_id=s.stage_id, course_name=STATE.cfg['character']['course_name'])
        messages = prompts.build_messages(system_prompt, history, text)

        s.add('user', text, kind=body.get('input_kind', 'text'))
        STATE.store.persist(s)
        STATE.clear_cancel(sid)

        self._sse_start()
        self._sse_send({'type': 'meta', 'context': ctx_meta, 'mode': mode,
                        'stage_id': s.stage_id, 'interaction_name': interactions.profile(s.stage_id)['name'],
                        'truncated_input': truncated,
                        'context_message_count': len(messages)})
        if ctx_meta.get('warning'):
            self._sse_send({'type': 'notice', 'message': ctx_meta['warning']})

        full = []
        try:
            gen, meta = STATE.llm.generate(messages, cancel_check=lambda: STATE.is_cancelled(sid))
            self._sse_send({'type': 'model', 'provider': meta.get('provider'), 'model': meta.get('model'),
                            'role': meta.get('role'), 'is_real_ai': meta.get('is_real_ai', False),
                            'degraded': meta.get('degraded', False),
                            'demo_label': meta.get('demo_label'), 'note': meta.get('note')})
            for delta in gen:
                if STATE.is_cancelled(sid):
                    break
                full.append(delta)
                self._sse_send({'type': 'delta', 'text': delta})
        except NotConfigured as e:
            self._sse_send({'type': 'error', 'code': 'not_configured', 'capability': e.capability,
                            'message': str(e.message)})
        except (UpstreamError, Exception) as e:  # noqa: B014
            self._sse_send({'type': 'error', 'code': 'upstream_error',
                            'message': cfgmod.redact(str(e))})

        answer = ''.join(full).strip()
        stopped = STATE.is_cancelled(sid)
        if answer:
            s.add('assistant', answer)
            STATE.store.persist(s)
        self._sse_send({'type': 'done', 'stopped': stopped, 'chars': len(answer),
                        'turns': s.turns(), 'session_id': sid})
        STATE.clear_cancel(sid)
        return self._sse_end()

    # ---------------- 语音 / 图片 ----------------
    def _asr(self):
        body = self._read_json()
        audio_b64 = body.get('audio_base64') or ''
        fmt = body.get('format') or 'wav'
        if not audio_b64:
            return self._send_json({'ok': False, 'error': 'no_audio', 'message': '未收到音频数据'}, 400)
        import base64
        try:
            raw = base64.b64decode(audio_b64)
        except Exception:
            return self._send_json({'ok': False, 'error': 'bad_audio', 'message': '音频 base64 解析失败'}, 400)
        try:
            res = STATE.asr.transcribe(raw, audio_format=fmt)
            return self._send_json({'ok': True, 'text': res['text'], 'provider': res.get('provider')})
        except NotConfigured as e:
            return self._send_json({'ok': False, 'error': 'not_configured', 'capability': 'asr',
                                    'message': str(e.message),
                                    'missing_params': STATE.asr.missing_params(),
                                    'provider_requirements': STATE.asr.status()['provider_requirements'],
                                    'hint': '语音对话链路需要 ASR；未配置时请使用文字输入。浏览器原生识别仅部分浏览器支持，且需 HTTPS。'}, 501)
        except UpstreamError as e:
            return self._send_json({'ok': False, 'error': 'upstream_error',
                                    'message': cfgmod.redact(str(e))}, 502)

    def _tts(self):
        body = self._read_json()
        text = (body.get('text') or '').strip()
        if not text:
            return self._send_json({'ok': False, 'error': 'no_text', 'message': '未收到文本'}, 400)
        try:
            res = STATE.tts.synthesize(text[:300])
            return self._send_bytes(res['audio'], res.get('mime', 'audio/mpeg'))
        except NotConfigured as e:
            return self._send_json({'ok': False, 'error': 'not_configured', 'capability': 'tts',
                                    'message': str(e.message),
                                    'missing_params': STATE.tts.missing_params(),
                                    'provider_requirements': STATE.tts.status()['provider_requirements'],
                                    'browser_fallback': STATE.tts.status()['browser_fallback']}, 501)
        except UpstreamError as e:
            return self._send_json({'ok': False, 'error': 'upstream_error',
                                    'message': cfgmod.redact(str(e))}, 502)

    def _vision(self):
        body = self._read_json()
        img_b64 = body.get('image_base64') or ''
        mime = body.get('mime') or 'image/jpeg'
        question = body.get('question')
        sid = body.get('session_id')
        vision_session = STATE.store.get(sid) if sid else None
        interaction_id = interactions.resolve_id(body.get('stage_id') or
                                                 (vision_session.stage_id if vision_session else None))
        if vision_session:
            vision_session.stage_id = interaction_id
        if not img_b64:
            return self._send_json({'ok': False, 'error': 'no_image', 'message': '未收到图片数据'}, 400)
        import base64
        try:
            raw = base64.b64decode(img_b64)
        except Exception:
            return self._send_json({'ok': False, 'error': 'bad_image', 'message': '图片 base64 解析失败'}, 400)
        max_mb = int(STATE.cfg['limits']['max_image_mb'])
        if len(raw) > max_mb * 1024 * 1024:
            return self._send_json({'ok': False, 'error': 'too_large',
                                    'message': f'图片超过 {max_mb}MB 上限，请压缩后再上传'}, 413)
        # 原图不落盘：仅在内存中处理
        try:
            text = STATE.vision.analyze(raw, mime, question=question,
                                       stage_id=interaction_id)
        except NotConfigured as e:
            return self._send_json({'ok': False, 'error': 'not_configured', 'capability': 'vision',
                                    'message': str(e.message),
                                    'note': 'DeepSeek 文本模型不支持图片输入，必须配置支持视觉的多模态模型。'}, 501)
        except UpstreamError as e:
            return self._send_json({'ok': False, 'error': 'upstream_error',
                                    'message': cfgmod.redact(str(e)), 'retryable': True}, 502)
        # 只保存文字分析结果与引用标签，不保存原图
        s = STATE.store.get(sid) if sid else None
        if s:
            label = f'照片#{len(s.image_refs) + 1}'
            s.add('user', f'[小朋友上传了{label}]\n附带问题：{question or "请看看这张照片"}',
                  kind='image', image_ref={'label': label, 'ts': time.time(),
                                           'description': text[:200]})
            s.add('assistant', text)
            s.prune_image_refs(int(STATE.cfg['limits'].get('max_image_refs', 5)))
            STATE.store.persist(s)
        return self._send_json({'ok': True, 'text': text, 'saved_original': False,
                                'note': '原图未保存，仅在服务端内存中临时处理。'})


def main():
    ap = argparse.ArgumentParser(description='《解锁大自然的隐身魔法》课程智能体后端')
    ap.add_argument('--host', default=None)
    ap.add_argument('--port', type=int, default=None)
    ap.add_argument('--demo', action='store_true', help='强制开启演示模式（规则回答，明确标注非真实 AI）')
    args = ap.parse_args()

    if args.demo:
        os.environ['APP_DEMO_MODE'] = '1'
        STATE.reload()
    # 云端（Render 等）注入标准 PORT，且需绑定 0.0.0.0；本地仍读 APP_PORT/APP_HOST。
    cloud_port = os.environ.get('PORT')
    host = args.host or os.environ.get('APP_HOST') or ('0.0.0.0' if cloud_port else STATE.cfg['server']['host'])
    port = args.port or int(cloud_port or os.environ.get('APP_PORT') or STATE.cfg['server']['port'])

    cap = cfgmod.capability_report(STATE.cfg)
    ip = netutil.primary_ip()
    print('=' * 68)
    print(' 《解锁大自然的隐身魔法》课程智能体 · 后端服务 v' + VERSION)
    print('=' * 68)
    print(f' 角色名称      : {STATE.cfg["character"]["name"]}')
    print(f' 监听地址      : http://{host}:{port}')
    print(f' 学生端(手机)  : http://{ip}:{port}/')
    print(f' 扫码入口单页  : http://{ip}:{port}/scan')
    print(f' 教师面板      : http://{ip}:{port}/teacher')
    print(f' 管理接口      : http://127.0.0.1:{port}/api/admin/network （仅本机）')
    print('-' * 68)
    print(f' 大模型        : {cap["llm"]["state"]} — {cap["llm"]["label"]}')
    print(f' 图片分析      : {cap["vision"]["state"]} — {cap["vision"]["label"]}')
    print(f' 语音识别 ASR  : {cap["asr"]["state"]} — {cap["asr"]["label"]}')
    print(f' 语音合成 TTS  : {cap["tts"]["state"]} — {cap["tts"]["label"]}')
    print(f' 配置文件      : {cfgmod.CONFIG_PATH}（{"存在" if os.path.isfile(cfgmod.CONFIG_PATH) else "不存在，使用默认值"}）')
    print('=' * 68)

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n正在停止服务...')
    finally:
        httpd.server_close()
        print('服务已停止。')


if __name__ == '__main__':
    main()
