# -*- coding: utf-8 -*-
"""多模态（图片分析）适配层。

严格约束：
- 只有配置了**确认支持图片输入的多模态模型**才可调用；未配置时抛 NotConfigured，
  上层必须返回“未配置”状态，绝不伪造分析成功。
- DeepSeek 的 deepseek-chat / deepseek-reasoner 为**纯文本模型，不支持图片输入**，
  因此不能用作图片分析（代码层面显式拦截，避免误配）。
- 输出必须把“照片中可见的观察”与“推测/猜想”分开；不得编造照片中不存在的证据。

接口形态（OpenAI 兼容多模态，豆包方舟/任意兼容服务均适用）：
POST {base_url}/chat/completions
{
  "model": "<vision-model>",
  "messages": [{"role":"user","content":[
      {"type":"text","text":"..."},
      {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}]}]
}
"""
import base64
import json
import urllib.error
import urllib.request

from .errors import NotConfigured, UpstreamError

TEXT_ONLY_MODELS = {
    'deepseek-chat', 'deepseek-reasoner', 'deepseek-coder',
}

VISION_SYSTEM_PROMPT = """你是一位幼儿园自然探究活动的观察助手。请分析幼儿上传的照片，输出严格分三段的中文结果：

【我看到的】（只写照片中**确实可见**的内容：主体、颜色、花纹、背景、位置关系。不得添加照片里没有的东西）
【可能的猜想】（基于可见内容提出 1-2 个与“保护色/颜色与环境是否相似”相关的猜想，用“可能”“也许”等措辞）
【可以问小朋友的一个问题】（只问一个问题，必须是幼儿能回答的、指向观察的问题）

硬性要求：
1. 不得编造照片中不存在的动物、颜色、花纹或证据。
2. 如果照片中没有与保护色相关的内容，或照片模糊无法判断，必须直接说明“这张照片看不太清楚，我们再拍一张试试？”，不要强行分析。
3. 不得给出确定性科学结论，只做观察描述与猜想。
4. 不得索要或推断幼儿个人身份信息。
5. 不出现任何技术术语。
"""


class VisionClient:
    def __init__(self, cfg):
        self.cfg = cfg

    def is_ready(self):
        v = self.cfg['vision']
        return bool(v.get('enabled')) and bool(str(v.get('api_key') or '').strip()) and bool(str(v.get('model') or '').strip())

    def _guard(self):
        v = self.cfg['vision']
        if not v.get('enabled'):
            raise NotConfigured('vision', '图片分析未启用：请在教师端配置并启用多模态模型')
        if not str(v.get('api_key') or '').strip():
            raise NotConfigured('vision', '图片分析未配置：缺少多模态模型 API 密钥')
        if not str(v.get('model') or '').strip():
            raise NotConfigured('vision', '图片分析未配置：缺少多模态模型名称（如豆包支持视觉输入的模型）')
        model = str(v.get('model')).strip().lower()
        if model in TEXT_ONLY_MODELS:
            raise NotConfigured('vision',
                                f'图片分析不可用：{model} 是纯文本模型，不支持图片输入。请改配支持视觉的模型。')

    def analyze(self, image_bytes, mime, question=None, stage_id=None):
        self._guard()
        v = self.cfg['vision']
        b64 = base64.b64encode(image_bytes).decode('ascii')
        text = VISION_SYSTEM_PROMPT
        if stage_id:
            text += f'\n当前教学环节 id：{stage_id}（幼儿园大班科学《解锁大自然的隐身魔法》，主题为保护色）。'
        if question:
            text += f'\n小朋友的附带问题：{question}（请结合照片回答，若照片无法回答就说明看不清楚）。'

        payload = {
            'model': v['model'],
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': text},
                    {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}},
                ],
            }],
            'temperature': 0.3,
            'max_tokens': 500,
        }
        if self.cfg.get('llm', {}).get('thinking_disabled', True):
            payload['thinking'] = {'type': 'disabled'}
        url = (v.get('base_url') or '').rstrip('/') + '/chat/completions'
        req = urllib.request.Request(
            url, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Authorization': f"Bearer {v['api_key']}"},
            method='POST')
        try:
            resp = urllib.request.urlopen(req, timeout=int(self.cfg['llm'].get('timeout_seconds', 60)))
            obj = json.loads(resp.read().decode('utf-8', 'ignore'))
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', 'ignore')[:500]
            except Exception:
                pass
            raise UpstreamError(f'图片分析上游错误 HTTP {e.code}: {body}', status=e.code)
        except Exception as e:
            raise UpstreamError(f'图片分析调用失败：{e}')

        try:
            return obj['choices'][0]['message']['content']
        except Exception:
            raise UpstreamError('图片分析返回格式异常')
