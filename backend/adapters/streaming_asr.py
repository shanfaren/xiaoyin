# -*- coding: utf-8 -*-
"""火山引擎流式语音识别 2.0（SAUC BigModel）WebSocket 适配器（纯标准库）。

浏览器不能直接携带密钥连接火山 WebSocket；由本地/云端后端建立连接，
前端按 200ms 左右把 16kHz、16bit、单声道 PCM 分片送给后端。
"""
import base64
import gzip
import json
import os
import socket
import ssl
import struct
import threading
import time
import uuid
from urllib.parse import urlparse

from .errors import NotConfigured, UpstreamError

PROTOCOL_VERSION = 0b0001
HEADER_SIZE = 0b0001

MSG_FULL_CLIENT_REQUEST = 0b0001
MSG_AUDIO_ONLY_REQUEST = 0b0010
MSG_FULL_SERVER_RESPONSE = 0b1001
MSG_SERVER_ACK = 0b1011
MSG_ERROR = 0b1111

FLAG_NONE = 0b0000
FLAG_LAST = 0b0010

SER_JSON = 0b0001
SER_NONE = 0b0000
COMP_NONE = 0b0000
COMP_GZIP = 0b0001


def _pack(msg_type, flags, payload, serialization=SER_NONE, compression=COMP_NONE):
    header = bytes([
        (PROTOCOL_VERSION << 4) | HEADER_SIZE,
        (msg_type << 4) | flags,
        (serialization << 4) | compression,
        0x00,
    ])
    return header + struct.pack('>I', len(payload)) + payload


def _unpack(data):
    if len(data) < 4:
        raise UpstreamError('流式识别返回头不完整')
    b0, b1, b2 = data[0], data[1], data[2]
    header_size = b0 & 0x0F
    msg_type = b1 >> 4
    flags = b1 & 0x0F
    compression = b2 & 0x0F
    offset = header_size * 4
    if flags & 0x01:  # 服务端带正序号时，先有 4 字节 sequence，再是 payload size
        offset += 4
    if len(data) < offset + 4:
        raise UpstreamError('流式识别返回长度字段不完整')
    size = struct.unpack('>I', data[offset:offset + 4])[0]
    body = data[offset + 4:offset + 4 + size]
    if compression == COMP_GZIP and body:
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    return msg_type, flags, body


class _WebSocket:
    """最小 WebSocket 客户端：仅二进制帧、掩码发送、ping/pong。"""

    def __init__(self, url, headers, timeout=15):
        u = urlparse(url)
        if u.scheme not in ('ws', 'wss'):
            raise UpstreamError('流式识别地址必须是 ws/wss')
        host = u.hostname
        port = u.port or (443 if u.scheme == 'wss' else 80)
        raw = socket.create_connection((host, port), timeout=timeout)
        if u.scheme == 'wss':
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=host)
        self.sock = raw
        self.buf = b''
        self.lock = threading.Lock()
        self._handshake(u, host, headers)

    def _handshake(self, u, host, headers):
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        path = u.path or '/'
        if u.query:
            path += '?' + u.query
        lines = [
            'GET %s HTTP/1.1' % path,
            'Host: %s' % host,
            'Upgrade: websocket',
            'Connection: Upgrade',
            'Sec-WebSocket-Key: %s' % key,
            'Sec-WebSocket-Version: 13',
        ]
        for k, v in headers.items():
            lines.append('%s: %s' % (k, v))
        self.sock.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode('utf-8'))
        raw = b''
        while b'\r\n\r\n' not in raw:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise UpstreamError('流式识别连接在握手阶段被关闭')
            raw += chunk
            if len(raw) > 65536:
                raise UpstreamError('流式识别握手响应过大')
        head, _, rest = raw.partition(b'\r\n\r\n')
        status = head.split(b'\r\n', 1)[0].decode('latin-1', 'ignore')
        if ' 101 ' not in status and not status.endswith(' 101'):
            raise UpstreamError('流式识别握手失败：' + status)
        self.buf = rest

    def _read_exact(self, n, timeout):
        self.sock.settimeout(timeout)
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise UpstreamError('流式识别连接已关闭')
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def send_binary(self, payload):
        frame = bytearray([0x82])
        length = len(payload)
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack('>H', length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack('>Q', length))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        with self.lock:
            self.sock.sendall(bytes(frame))

    def _send_pong(self, payload):
        frame = bytearray([0x8A])
        length = len(payload)
        frame.append(0x80 | length)
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        with self.lock:
            self.sock.sendall(bytes(frame))

    def recv_binary(self, timeout=10):
        while True:
            h = self._read_exact(2, timeout)
            opcode = h[0] & 0x0F
            masked = h[1] & 0x80
            length = h[1] & 0x7F
            if length == 126:
                length = struct.unpack('>H', self._read_exact(2, timeout))[0]
            elif length == 127:
                length = struct.unpack('>Q', self._read_exact(8, timeout))[0]
            mask = self._read_exact(4, timeout) if masked else b''
            data = self._read_exact(length, timeout)
            if masked:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 0x8:
                raise UpstreamError('流式识别连接已关闭')
            if opcode == 0x9:
                self._send_pong(data)
                continue
            if opcode == 0xA:
                continue
            return data

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class StreamingSession:
    def __init__(self, ws):
        self.ws = ws
        self.text = ''
        self.closed = False
        self.error = ''

    def push(self, pcm):
        if self.closed:
            return self.text
        if pcm:
            self.ws.send_binary(_pack(MSG_AUDIO_ONLY_REQUEST, FLAG_NONE, pcm))
        self._drain()
        return self.text

    def finish(self):
        if self.closed:
            return self.text
        try:
            self.ws.send_binary(_pack(MSG_AUDIO_ONLY_REQUEST, FLAG_LAST, b''))
        except Exception:
            pass
        deadline = time.time() + 20
        while not self.closed and time.time() < deadline:
            try:
                self._read_one(min(5, max(0.2, deadline - time.time())))
            except Exception as e:
                self.error = str(e)
                break
        self.close()
        return self.text

    def _drain(self):
        while True:
            try:
                self._read_one(0.35)
            except socket.timeout:
                return
            except Exception as e:
                self.error = str(e)
                return

    def _read_one(self, timeout):
        data = self.ws.recv_binary(timeout)
        msg_type, flags, body = _unpack(data)
        if msg_type == MSG_ERROR:
            raise UpstreamError('流式识别错误：' + body.decode('utf-8', 'ignore')[:300])
        if msg_type in (MSG_FULL_SERVER_RESPONSE, MSG_SERVER_ACK):
            try:
                obj = json.loads(body.decode('utf-8', 'ignore'))
            except Exception:
                return
            result = obj.get('result') or {}
            text = result.get('text')
            if text:
                self.text = text
            if flags & FLAG_LAST:
                self.closed = True

    def close(self):
        self.closed = True
        self.ws.close()


class StreamingASRClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sec = cfg.get('streaming_asr') or {}
        self.asr = cfg.get('asr') or {}

    def _api_key(self):
        return str(self.sec.get('api_key') or self.asr.get('api_key') or '').strip()

    def is_ready(self):
        enabled = self.sec.get('enabled', False)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(enabled and self._api_key())

    def open(self):
        if not self.is_ready():
            raise NotConfigured('streaming_asr', '流式语音识别未配置')
        url = str(self.sec.get('base_url') or 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel').strip()
        resource_id = str(self.sec.get('resource_id') or 'volc.bigasr.sauc.duration').strip()
        app_id = str(self.sec.get('app_id') or self.asr.get('app_id') or '').strip()
        api_key = self._api_key()
        headers = {
            'X-Api-Resource-Id': resource_id,
            'X-Api-Connect-Id': str(uuid.uuid4()),
        }
        if app_id:
            headers['X-Api-App-Key'] = app_id
            headers['X-Api-Access-Key'] = api_key
        else:
            headers['X-Api-Key'] = api_key
        ws = _WebSocket(url, headers)
        config = {
            'user': {'uid': app_id or 'xiaoyin'},
            'audio': {'format': 'pcm', 'rate': 16000, 'bits': 16, 'channel': 1, 'codec': 'raw'},
            'request': {'model_name': 'bigmodel', 'enable_punc': True, 'enable_itn': True},
        }
        ws.send_binary(_pack(
            MSG_FULL_CLIENT_REQUEST, FLAG_NONE,
            json.dumps(config, ensure_ascii=False).encode('utf-8'), SER_JSON))
        return StreamingSession(ws)
