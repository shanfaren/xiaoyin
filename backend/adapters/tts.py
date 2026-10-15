# -*- coding: utf-8 -*-
"""语音合成（TTS）适配层。

用户已确认将提供「语音合成 API」，但**尚未提供具体供应商与鉴权参数**，
因此当前状态为「未配置」，界面必须明确显示未配置，不得声称已接通。

已实现的适配器：
- volcengine：火山引擎语音合成（POST /api/v1/tts，Authorization: Bearer;<access_token>，
  body 含 app.appid / app.token / app.cluster / user.uid / audio.voice_type / request.text）。
  **注意**：cluster 与 voice_type 的具体取值必须由用户在控制台确认后填入；本适配器不做猜测。
- openai_compatible：POST {base_url}/audio/speech，body {model, input, voice, response_format}，返回二进制音频。

未实现的供应商（aliyun / tencent / xfyun）会返回 NotConfigured 并列出所需参数，避免伪成功。
"""
import base64
import json
import urllib.error
import urllib.request
import uuid

from .errors import NotConfigured, UpstreamError

PROVIDER_REQUIRED = {
    'volcengine': [
        ('app_id', '火山引擎控制台 → 语音合成 → APP ID'),
        ('api_key（Access Token）', '火山引擎控制台 → 语音合成 → Access Token'),
        ('cluster', '如 volcano_tts（大模型语音合成）/ volcano_mega；**须以控制台实际开通的 cluster 为准**'),
        ('voice', '音色 voice_type，如 BV700_streaming 等；**须以控制台音色列表为准**'),
        ('base_url', '默认 https://openspeech.bytedance.com/api/v1/tts'),
    ],
    'openai_compatible': [
        ('base_url', '如 https://api.openai.com/v1'),
        ('api_key', '对应服务密钥'),
        ('model', '如 tts-1'),
        ('voice', '如 alloy'),
    ],
    'aliyun': [
        ('app_key', '阿里云智能语音交互项目 Appkey'),
        ('access_token 或 (access_key_id + access_key_secret)', '阿里云 RAM 凭证'),
        ('voice', '发音人，如 aixia'),
    ],
    'tencent': [
        ('secret_id / secret_key', '腾讯云访问密钥'),
        ('app_id', '腾讯云语音合成 AppId'),
        ('voice', '音色 ID'),
    ],
    'xfyun': [
        ('app_id / api_key / api_secret', '讯飞开放平台凭证'),
        ('voice', '发音人，如 xiaoyan'),
    ],
    'volcengine_seedtts': [
        ('api_key（X-Api-Key）', '大模型语音合成 2.0 的 API Key'),
        ('base_url', '默认 https://openspeech.bytedance.com/api/v3/tts/unidirectional'),
        ('resource_id', '固定 seed-tts-2.0（请求头 X-Api-Resource-Id）'),
        ('voice', '音色 speaker，如 zh_male_taocheng_uranus_bigtts（青年男声）'),
    ],
}

SUPPORTED = ('volcengine', 'volcengine_seedtts', 'openai_compatible')


class TTSClient:
    def __init__(self, cfg):
        self.cfg = cfg

    def is_ready(self):
        t = self.cfg['tts']
        if not t.get('enabled'):
            return False
        if not str(t.get('base_url') or '').strip():
            return False
        if not str(t.get('api_key') or '').strip():
            return False
        prov = (t.get('provider') or '').strip().lower()
        if prov == 'volcengine':
            return bool(str(t.get('app_id') or '').strip() and str(t.get('voice') or '').strip())
        if prov == 'volcengine_seedtts':
            return bool(str(t.get('api_key') or '').strip() and str(t.get('voice') or '').strip())
        if prov == 'openai_compatible':
            return bool(str(t.get('model') or '').strip() and str(t.get('voice') or '').strip())
        return False

    def missing_params(self):
        t = self.cfg['tts']
        prov = (t.get('provider') or '').strip().lower()
        need = PROVIDER_REQUIRED.get(prov)
        if need is None:
            return ['provider（供应商未选择：volcengine / openai_compatible / aliyun / tencent / xfyun）',
                    'base_url', 'api_key', 'voice']
        miss = []
        if not str(t.get('base_url') or '').strip():
            miss.append('base_url')
        if not str(t.get('api_key') or '').strip():
            miss.append('api_key')
        if not str(t.get('voice') or '').strip():
            miss.append('voice')
        if prov == 'volcengine':
            if not str(t.get('app_id') or '').strip():
                miss.append('app_id')
            if not str(t.get('cluster') or '').strip():
                miss.append('cluster')
        if prov == 'volcengine_seedtts' and not str(t.get('resource_id') or '').strip():
            miss.append('resource_id')
        if prov == 'openai_compatible' and not str(t.get('model') or '').strip():
            miss.append('model')
        return miss

    def _guard(self):
        t = self.cfg['tts']
        if not t.get('enabled'):
            raise NotConfigured('tts', '语音合成（TTS）未配置：无法进行语音播报，可先用浏览器朗读（备选）')
        miss = self.missing_params()
        if miss:
            raise NotConfigured('tts', '语音合成（TTS）参数不完整，缺少：' + '、'.join(miss))
        prov = (t.get('provider') or '').strip().lower()
        if prov not in SUPPORTED:
            raise NotConfigured('tts', f'语音合成供应商 {prov} 的适配器尚未实现，当前仅实现：{" / ".join(SUPPORTED)}')

    def synthesize(self, text, voice=None):
        self._guard()
        t = self.cfg['tts']
        prov = (t.get('provider') or '').strip().lower()
        if prov == 'volcengine':
            return self._volcengine(text, voice)
        if prov == 'volcengine_seedtts':
            return self._seedtts(text, voice)
        if prov == 'openai_compatible':
            return self._openai_compatible(text, voice)
        raise NotConfigured('tts', f'未实现的供应商：{prov}')

    def _volcengine(self, text, voice=None):
        t = self.cfg['tts']
        url = str(t.get('base_url') or 'https://openspeech.bytedance.com/api/v1/tts').strip()
        req_id = str(uuid.uuid4())
        body = {
            'app': {'appid': t.get('app_id', ''), 'token': t.get('api_key', ''), 'cluster': t.get('cluster', '')},
            'user': {'uid': str(t.get('app_id') or 'xiaoyin')},
            'audio': {'voice_type': voice or t.get('voice', ''), 'encoding': 'mp3', 'speed_ratio': 1.0},
            'request': {'reqid': req_id, 'text': text, 'operation': 'query'},
        }
        headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer;{t.get('api_key', '')}"}
        req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     headers=headers, method='POST')
        try:
            resp = urllib.request.urlopen(req, timeout=int(self.cfg['llm'].get('timeout_seconds', 60)))
            raw = resp.read()
        except urllib.error.HTTPError as e:
            raise UpstreamError(f'语音合成上游错误 HTTP {e.code}', status=e.code)
        except Exception as e:
            raise UpstreamError(f'语音合成调用失败：{e}')
        try:
            obj = json.loads(raw.decode('utf-8', 'ignore'))
        except Exception:
            return {'audio': raw, 'mime': 'audio/mpeg', 'provider': 'volcengine'}
        code = obj.get('code')
        if code not in (3000, '3000'):
            raise UpstreamError(f"语音合成失败：code={code} message={obj.get('message')}")
        data_b64 = obj.get('data')
        if not data_b64:
            raise UpstreamError('语音合成未返回音频数据')
        return {'audio': base64.b64decode(data_b64), 'mime': 'audio/mpeg',
                'provider': 'volcengine', 'request_id': req_id}

    def _seedtts(self, text, voice=None):
        """大模型语音合成 2.0：v3 unidirectional，X-Api-Key + X-Api-Resource-Id。
        返回按行 JSON 帧，每帧 data 字段为 base64 音频分片，需拼包。"""
        t = self.cfg['tts']
        url = str(t.get('base_url') or 'https://openspeech.bytedance.com/api/v3/tts/unidirectional').strip()
        resource_id = str(t.get('resource_id') or 'seed-tts-2.0').strip()
        speaker = voice or t.get('voice', '')
        body = {
            'user': {'uid': 'xiaoyin'},
            'req_params': {
                'text': text,
                'speaker': speaker,
                'audio_params': {'format': 'mp3', 'sample_rate': 16000,
                                 'speech_rate': int(t.get('speech_rate', -10))},
            },
        }
        if t.get('context_texts'):
            body['req_params']['context_texts'] = list(t['context_texts'])
        headers = {
            'Content-Type': 'application/json',
            'X-Api-Key': str(t.get('api_key', '')),
            'X-Api-Resource-Id': resource_id,
        }
        req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     headers=headers, method='POST')
        chunks = []
        try:
            resp = urllib.request.urlopen(req, timeout=int(self.cfg['llm'].get('timeout_seconds', 60)))
            for raw_line in resp:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode('utf-8', 'ignore'))
                except Exception:
                    continue
                if obj.get('data'):
                    try:
                        chunks.append(base64.b64decode(obj['data']))
                    except Exception:
                        pass
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                detail = e.read().decode('utf-8', 'ignore')[:300]
            except Exception:
                pass
            raise UpstreamError(f'语音合成上游错误 HTTP {e.code}: {detail}', status=e.code)
        except Exception as e:
            raise UpstreamError(f'语音合成调用失败：{e}')
        if not chunks:
            raise UpstreamError('语音合成未返回音频数据（seed-tts 无分片）')
        return {'audio': b''.join(chunks), 'mime': 'audio/mpeg',
                'provider': 'volcengine_seedtts', 'voice': speaker}

    def _openai_compatible(self, text, voice=None):
        t = self.cfg['tts']
        url = (t.get('base_url') or '').rstrip('/') + '/audio/speech'
        body = {'model': t.get('model', ''), 'input': text,
                'voice': voice or t.get('voice', ''), 'response_format': t.get('format', 'mp3')}
        headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {t.get('api_key', '')}"}
        req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     headers=headers, method='POST')
        try:
            resp = urllib.request.urlopen(req, timeout=int(self.cfg['llm'].get('timeout_seconds', 60)))
            return {'audio': resp.read(), 'mime': 'audio/mpeg', 'provider': 'openai_compatible'}
        except urllib.error.HTTPError as e:
            raise UpstreamError(f'语音合成上游错误 HTTP {e.code}', status=e.code)
        except Exception as e:
            raise UpstreamError(f'语音合成调用失败：{e}')

    def status(self):
        t = self.cfg['tts']
        return {
            'configured': self.is_ready(),
            'provider': t.get('provider') or '',
            'voice': t.get('voice') or '',
            'missing_params': self.missing_params(),
            'provider_requirements': PROVIDER_REQUIRED,
            'browser_fallback': '浏览器 speechSynthesis 朗读为备选方案，中文音色依赖终端系统语音包，效果不稳定，仅作降级。',
        }
