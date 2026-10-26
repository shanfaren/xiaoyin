# -*- coding: utf-8 -*-
"""LLM 适配层：OpenAI 兼容 /chat/completions（豆包方舟、DeepSeek、任意兼容服务）。

特性：
- 主模型 / 备用模型自动降级；
- 超时、重试、流式响应；
- 可取消（停止生成）；
- 演示模式：使用课程知识库的规则化回答，**明确标注非真实 AI**。

官方接口参考（用于配置说明，不在此硬编码密钥）：
- 豆包（火山方舟）：POST {base_url}/chat/completions，Authorization: Bearer <ARK_API_KEY>，
  model 可填推理接入点 ID（ep-...）或模型名称。
- DeepSeek：POST https://api.deepseek.com/chat/completions，Authorization: Bearer <DEEPSEEK_API_KEY>，
  model=deepseek-chat（对话）/ deepseek-reasoner（推理）。
"""
import json
import time
import urllib.error
import urllib.request
from backend.adapters.network import open_request

from .errors import NotConfigured, UpstreamError, TimeoutError_

SSE_DATA_PREFIX = 'data:'


def _auth_header(provider, api_key):
    if provider == 'doubao' or provider == 'ark':
        return {'Authorization': f'Bearer {api_key}'}
    if provider == 'deepseek':
        return {'Authorization': f'Bearer {api_key}'}
    return {'Authorization': f'Bearer {api_key}'}


def _chat_url(base_url):
    b = (base_url or '').rstrip('/')
    if b.endswith('/chat/completions'):
        return b
    return b + '/chat/completions'


class LLMClient:
    def __init__(self, cfg, demo_responder=None):
        self.cfg = cfg
        self.demo_responder = demo_responder

    # ---------- 配置可用性 ----------
    def _candidates(self):
        out = []
        p = self.cfg['llm']['primary']
        key = str(p.get('api_key') or '').strip()
        model = str(p.get('endpoint_id') or p.get('model') or '').strip()
        if key and model:
            out.append({'role': 'primary', 'provider': p.get('provider', 'doubao'),
                        'base_url': p.get('base_url', ''), 'model': model, 'api_key': key})
        f = self.cfg['llm']['fallback']
        fkey = str(f.get('api_key') or '').strip()
        fmodel = str(f.get('model') or '').strip()
        if fkey and fmodel:
            out.append({'role': 'fallback', 'provider': f.get('provider', 'deepseek'),
                        'base_url': f.get('base_url', ''), 'model': fmodel, 'api_key': fkey})
        return out

    def is_ready(self):
        return len(self._candidates()) > 0

    def is_demo(self):
        return bool(self.cfg['modes']['demo'])

    # ---------- 生成 ----------
    def generate(self, messages, cancel_check=None):
        """返回 (delta_iter, meta)。meta 含实际使用的 provider/model/降级信息。
        delta_iter 产出文本增量；若全部候选失败且开启演示模式，则回退到演示回答。
        """
        # --demo 为“强制演示模式”：无论是否配置了有效密钥，都走规则回答并明确标注非真实 AI。
        if self.is_demo():
            return self._demo_stream(messages, cancel_check), {
                'provider': 'demo', 'model': 'rule-based', 'role': 'demo',
                'degraded': False, 'is_real_ai': False,
                'demo_label': self.cfg['modes']['demo_label'],
                'note': '演示模式：以下内容由课程知识库规则生成，不是真实大模型回答。',
                'errors': [],
            }
        cands = self._candidates()
        errors = []
        for cand in cands:
            try:
                gen, meta = self._stream_one(cand, messages, cancel_check)
                # 先取第一个增量以确认连接成功，再交给上层
                first = next(gen, None)
                meta['degraded'] = (cand['role'] == 'fallback')

                def chained(first=first, gen=gen):
                    if first:
                        yield first
                    for d in gen:
                        yield d

                return chained(), meta
            except (UpstreamError, TimeoutError_, urllib.error.URLError, OSError, ValueError) as e:
                errors.append(f"{cand['role']}:{type(e).__name__}:{e}")
                continue

        if self.is_demo():
            return self._demo_stream(messages, cancel_check), {
                'provider': 'demo', 'model': 'rule-based', 'role': 'demo',
                'degraded': True, 'is_real_ai': False,
                'demo_label': self.cfg['modes']['demo_label'],
                'note': '演示模式：以下内容由课程知识库规则生成，不是真实大模型回答。',
                'errors': errors,
            }
        if not cands:
            raise NotConfigured('llm', '未配置任何可用模型（需要 base_url + model + api_key）')
        raise UpstreamError('所有模型均调用失败：' + ' | '.join(errors))

    def _stream_one(self, cand, messages, cancel_check):
        payload = {
            'model': cand['model'],
            'messages': messages,
            'stream': bool(self.cfg['llm']['stream']),
            'temperature': self.cfg['llm'].get('temperature', 0.6),
            'max_tokens': self.cfg['llm'].get('max_tokens', 512),
        }
        # doubao-seed-evolving 默认输出大量隐藏推理（首字延迟可达 20-30s）；
        # 课堂场景关闭推理，首字 1-2s，与牙仙子月月表现一致。
        if self.cfg['llm'].get('thinking_disabled', True):
            payload['thinking'] = {'type': 'disabled'}
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
        headers.update(_auth_header(cand['provider'], cand['api_key']))
        url = _chat_url(cand['base_url'])
        timeout = self.cfg['llm'].get('timeout_seconds', 60)
        retries = int(self.cfg['llm'].get('max_retries', 2))

        last_err = None
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            try:
                resp = open_request(req, timeout=timeout)
                break
            except urllib.error.HTTPError as e:
                body = ''
                try:
                    body = e.read().decode('utf-8', 'ignore')[:500]
                except Exception:
                    pass
                last_err = UpstreamError(f'HTTP {e.code} {e.reason} {body}', status=e.code, body=body)
                if e.code in (400, 401, 403, 404):
                    raise last_err  # 配置类错误不重试
                time.sleep(0.6 * (attempt + 1))
            except urllib.error.URLError as e:
                last_err = UpstreamError(f'网络错误 {e.reason}')
                time.sleep(0.6 * (attempt + 1))
            except TimeoutError as e:  # noqa: F841  socket timeout
                last_err = TimeoutError_('请求超时')
                time.sleep(0.6 * (attempt + 1))
        else:
            raise last_err or UpstreamError('未知错误')

        meta = {'provider': cand['provider'], 'model': cand['model'], 'role': cand['role'],
                'is_real_ai': True, 'degraded': False}

        def delta_iter(resp=resp, cancel_check=cancel_check):
            try:
                for raw in resp:
                    if cancel_check and cancel_check():
                        break
                    line = raw.decode('utf-8', 'ignore').strip()
                    if not line or not line.startswith(SSE_DATA_PREFIX):
                        continue
                    chunk = line[len(SSE_DATA_PREFIX):].strip()
                    if chunk == '[DONE]':
                        break
                    try:
                        obj = json.loads(chunk)
                    except Exception:
                        continue
                    choices = obj.get('choices') or []
                    if not choices:
                        continue
                    delta = choices[0].get('delta') or {}
                    piece = delta.get('content')
                    if piece:
                        yield piece
            finally:
                try:
                    resp.close()
                except Exception:
                    pass

        return delta_iter(), meta

    # ---------- 演示模式（规则化，明确标注） ----------
    def _demo_stream(self, messages, cancel_check):
        text = self.demo_responder(messages) if self.demo_responder else \
            '（演示模式）我暂时还没有接入真实的 AI 大脑，先请老师帮我配置一下吧。'
        step = 6
        for i in range(0, len(text), step):
            if cancel_check and cancel_check():
                break
            time.sleep(0.02)
            yield text[i:i + step]


def summarize(client, history_text, budget_hint=1200):
    """用主模型对超长历史做摘要（用于 token 预算控制）。
    未配置模型时返回 None，由上层按“保留最近 N 轮完整 + 丢弃更早”的降级策略处理。
    """
    if not client.is_ready():
        return None
    sys_msg = {'role': 'system', 'content': '你是课程会话摘要助手。请用不超过 120 字的中文，'
                                            '概括以下师生对话中的关键事实（学生问过什么、智能体解释过什么、'
                                            '学生已掌握与仍困惑的点）。只输出摘要正文。'}
    msgs = [sys_msg, {'role': 'user', 'content': history_text[:6000]}]
    try:
        gen, _meta = client.generate(msgs)
        return ''.join(gen).strip() or None
    except Exception:
        return None
