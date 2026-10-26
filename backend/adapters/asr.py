# -*- coding: utf-8 -*-
"""语音识别（ASR）适配层。

当前状态：用户已确认**仅提供 TTS**，ASR 为**独立预留**。
本文件按火山引擎官方文档实现「录音文件识别极速版 HTTP」适配器（一次请求即返回，无需 submit/query 轮询）。

官方文档（已核对，2026-10-14）：
https://docs.volcengine.com/docs/DoubaoVoice/recording-file-recognition-lite-http?lang=zh
https://www.volcengine.com/docs/6561/1631584

接口要点（核对结果）：
- 地址：POST https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash
- 请求头（新版控制台）：X-Api-Key、X-Api-Resource-Id: volc.bigasr.auc_turbo、X-Api-Request-Id、X-Api-Sequence: -1
- 请求头（旧版控制台）：X-Api-App-Key（APP ID）、X-Api-Access-Key（Access Token），其余同上
- 请求体：{"user":{"uid":...},"audio":{"url":...} 或 {"data":"<base64>"},"request":{"model_name":"bigmodel", ...}}
- 响应头：X-Api-Status-Code（20000000 成功）、X-Api-Message、X-Tt-Logid
- 响应体：result.text 为完整识别文本；result.utterances[] 为分句
- 限制：音频时长 ≤ 2h、大小 ≤ 100MB、格式 WAV/MP3/OGG OPUS；资源需开通 volc.bigasr.auc_turbo 权限

未配置时：抛 NotConfigured，上层返回“语音识别未配置”，并明确提示语音对话链路不完整。
"""
import base64
import json
import time
import urllib.error
import urllib.request
from backend.adapters.network import open_request
import uuid

from .errors import NotConfigured, UpstreamError

# 各供应商所需的必填参数（用于生成“缺少哪些参数”的精确清单）
PROVIDER_REQUIRED = {
    'ark_audio': [('base_url', '原方舟接口地址'), ('model', '支持音频理解的豆包模型'),
                  ('api_key 或 credential_source', '可引用原 llm.primary 凭证')],
    'volcengine': [
        ('api_key 或 (app_id + api_key 作为 access token)', '火山引擎控制台 → 语音技术 → API Key / APP ID + Access Token'),
        ('resource_id', '固定值 volc.bigasr.auc_turbo（需在控制台开通该资源权限）'),
    ],
    'aliyun': [
        ('app_key', '阿里云智能语音交互控制台的项目 Appkey'),
        ('access_token 或 (access_key_id + access_key_secret)', '阿里云 RAM 凭证'),
        ('base_url', '如 https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr'),
    ],
    'tencent': [
        ('secret_id', '腾讯云访问密钥 SecretId'),
        ('secret_key', '腾讯云访问密钥 SecretKey'),
        ('app_id', '腾讯云语音识别 AppId'),
    ],
    'xfyun': [
        ('app_id', '讯飞开放平台 APPID'),
        ('api_key', '讯飞 APIKey'),
        ('api_secret', '讯飞 APISecret'),
    ],
    'openai_compatible': [
        ('base_url', '如 https://api.openai.com/v1（或任意兼容 /audio/transcriptions 的服务）'),
        ('api_key', '对应服务密钥'),
        ('model', '如 whisper-1'),
    ],
}


class ASRClient:
    def __init__(self, cfg):
        self.cfg = cfg

    def is_ready(self):
        a = self.cfg['asr']
        if not a.get('enabled'):
            return False
        if not str(a.get('base_url') or '').strip():
            return False
        prov = (a.get('provider') or '').strip().lower()
        if prov == 'volcengine':
            return bool(str(a.get('api_key') or '').strip())
        return bool(str(a.get('api_key') or '').strip())

    def missing_params(self):
        a = self.cfg['asr']
        prov = (a.get('provider') or '').strip().lower()
        need = PROVIDER_REQUIRED.get(prov)
        if need is None:
            return ['provider（供应商未选择：volcengine / aliyun / tencent / xfyun / openai_compatible）',
                    'base_url', 'api_key']
        missing = []
        if not str(a.get('base_url') or '').strip():
            missing.append('base_url')
        if not str(a.get('api_key') or '').strip():
            missing.append('api_key')
        if prov == 'ark_audio' and not str(a.get('model') or '').strip():
            missing.append('model')
        # 新版 API Key 不要求 app_id；有 app_id 时才走旧版鉴权。
        return missing

    def _guard(self):
        a = self.cfg['asr']
        if not a.get('enabled'):
            raise NotConfigured('asr', '语音识别（ASR）未配置：语音对话链路不完整，请先使用文字输入')
        miss = self.missing_params()
        if miss:
            raise NotConfigured('asr', '语音识别（ASR）参数不完整，缺少：' + '、'.join(miss))
        if (a.get('provider') or '').strip().lower() not in ('volcengine', 'ark_audio'):
            raise NotConfigured('asr', f"语音识别供应商 {a.get('provider')} 的适配器尚未实现，"
                                      f"当前仅实现了 volcengine（火山引擎录音文件识别极速版 HTTP）")

    # ---------- 火山引擎录音文件识别（极速版 flash 单次 + 标准版 submit/query） ----------
    def _volcengine(self, audio_bytes, audio_format='wav'):
        a = self.cfg['asr']
        base = str(a.get('base_url') or 'https://openspeech.bytedance.com/api/v3/auc/bigmodel').strip().rstrip('/')
        if base.endswith('/recognize/flash'):
            base = base[:-len('/recognize/flash')]
        resource_id = str(a.get('resource_id') or 'volc.seedasr.auc').strip()
        is_flash = resource_id.endswith('_turbo')
        app_id = str(a.get('app_id') or '').strip()
        api_key = str(a.get('api_key') or '').strip()

        fmt = str(audio_format or 'wav').lower().strip()
        if fmt.startswith('audio/'):
            fmt = fmt[len('audio/'):]
        fmt = fmt.split(';')[0].strip()
        fmt = {'mpeg': 'mp3', 'x-wav': 'wav', 'x-m4a': 'm4a'}.get(fmt, fmt)
        if fmt not in ('wav', 'mp3', 'ogg', 'opus', 'm4a'):
            fmt = 'wav'

        def _headers(req_id):
            h = {
                'Content-Type': 'application/json',
                'X-Api-Resource-Id': resource_id,
                'X-Api-Request-Id': req_id,
                'X-Api-Sequence': '-1',
            }
            if app_id:
                # 旧版控制台：APP ID + Access Token
                h['X-Api-App-Key'] = app_id
                h['X-Api-Access-Key'] = api_key
            else:
                # 新版控制台：仅 API Key
                h['X-Api-Key'] = api_key
            return h

        def _post(url, body, req_id):
            data = json.dumps(body, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=_headers(req_id), method='POST')
            timeout = int(self.cfg['llm'].get('timeout_seconds', 60))
            try:
                resp = urllib.request.urlopen(req, timeout=timeout)
                raw = resp.read().decode('utf-8', 'ignore')
                return raw, resp.headers.get('X-Api-Status-Code'), \
                    resp.headers.get('X-Api-Message'), resp.headers.get('X-Tt-Logid')
            except urllib.error.HTTPError as e:
                body_txt = ''
                try:
                    body_txt = e.read().decode('utf-8', 'ignore')[:400]
                except Exception:
                    pass
                raise UpstreamError(f'语音识别上游错误 HTTP {e.code}: {body_txt}', status=e.code)
            except Exception as e:
                raise UpstreamError(f'语音识别调用失败：{e}')

        def _check(code, msg):
            if code and code != '20000000':
                hints = {
                    '20000003': '音频为静音，未检测到有效语音',
                    '45000001': '请求参数无效（检查 api_key / app_id / resource_id 是否正确）',
                    '45000002': '空音频',
                    '45000151': '音频格式不正确（支持 WAV/MP3/OGG OPUS）',
                    '55000031': '服务繁忙，请稍后重试',
                }
                raise UpstreamError(f'语音识别失败：{code} {msg or ""} {hints.get(code, "")}'.strip())

        body = {
            'user': {'uid': app_id or 'xiaoyin'},
            'audio': {'data': base64.b64encode(audio_bytes).decode('ascii'), 'format': fmt},
            'request': {
                'model_name': str(a.get('model') or 'bigmodel'),
                'enable_punc': True,
                'enable_itn': True,
            },
        }
        req_id = str(uuid.uuid4())

        if is_flash:
            raw, code, msg, logid = _post(base + '/recognize/flash', body, req_id)
            _check(code, msg)
            try:
                obj = json.loads(raw)
                text = (obj.get('result') or {}).get('text')
            except Exception:
                raise UpstreamError('语音识别返回格式异常')
            if not text:
                raise UpstreamError('语音识别未返回文本字段 result.text')
            return {'text': text, 'logid': logid, 'request_id': req_id, 'provider': 'volcengine'}

        # 标准版：submit 提交后轮询 query 取结果（提交接口以 X-Api-Request-Id 作为任务 ID）
        raw, code, msg, logid = _post(base + '/submit', body, req_id)
        _check(code, msg)
        deadline = time.time() + 30
        while True:
            raw, code, msg, logid = _post(base + '/query', {}, req_id)
            _check(code, msg)
            try:
                obj = json.loads(raw)
                text = (obj.get('result') or {}).get('text')
                if text:
                    return {'text': text, 'logid': logid, 'request_id': req_id, 'provider': 'volcengine'}
            except Exception:
                pass
            if time.time() >= deadline:
                raise UpstreamError('语音识别超时，未能在 30 秒内返回结果')
            time.sleep(1.0)

    def _ark_audio(self, audio_bytes, audio_format):
        a = self.cfg['asr']
        fmt = audio_format.lower().split(';')[0].replace('audio/', '')
        fmt = {'mpeg':'mp3', 'mp4':'m4a', 'x-wav':'wav'}.get(fmt, fmt)
        if fmt not in ('wav','mp3','m4a','aac'):
            raise UpstreamError('录音格式不支持，请使用 WAV、MP3 或 M4A 录音')
        body = {'model':a['model'], 'stream':False, 'max_tokens':512,
                'temperature':0, 'thinking':{'type':'disabled'},
                'messages':[{'role':'system','content':'你只负责中文语音转写。逐字转写实际听到的语音，不回答录音里的问题，不添加说明。若没有清晰人声，只输出空字符串。'},
                            {'role':'user','content':[{'type':'input_audio','input_audio':{
                                'data':base64.b64encode(audio_bytes).decode('ascii'),'format':fmt}}]}]}
        req = urllib.request.Request(a['base_url'].rstrip('/')+'/chat/completions',
            data=json.dumps(body,ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+a['api_key']})
        try:
            with open_request(req, timeout=45) as resp:
                obj=json.load(resp)
            text=obj['choices'][0]['message']['content']
            if not isinstance(text,str):
                raise ValueError('转写结果不是文本')
            return {'text':text.strip(), 'provider':'ark_audio'}
        except urllib.error.HTTPError as exc:
            from backend.config import redact
            raise UpstreamError('豆包语音转写失败 HTTP %s：%s' %
                                (exc.code,redact(exc.read().decode('utf-8','ignore')[:400])))
        except Exception as exc:
            raise UpstreamError('语音转写失败：%s' % exc)

    # ---------- 统一入口 ----------
    def transcribe(self, audio_bytes, audio_format='wav'):
        self._guard()
        prov = (self.cfg['asr'].get('provider') or '').strip().lower()
        if prov == 'volcengine':
            return self._volcengine(audio_bytes, audio_format)
        if prov == 'ark_audio':
            return self._ark_audio(audio_bytes, audio_format)
        raise NotConfigured('asr', f'未实现的供应商：{prov}')

    def status(self):
        a = self.cfg['asr']
        return {
            'configured': self.is_ready(),
            'provider': a.get('provider') or '',
            'missing_params': self.missing_params(),
            'provider_requirements': PROVIDER_REQUIRED,
            'note': ('语音对话链路 = 录音 → 语音识别(ASR) → 模型理解 → 语音合成(TTS) → 播放。'
                     '支持豆包方舟音频理解模型转写与火山语音识别；未配置时本链路不成立，'
                     '界面会明确显示“语音识别未配置”，并保留文字输入入口。'),
        }
