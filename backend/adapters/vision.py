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
from .network import open_request

from .errors import NotConfigured, UpstreamError

TEXT_ONLY_MODELS = {
    'deepseek-chat', 'deepseek-reasoner', 'deepseek-coder',
}

VISION_SYSTEM_PROMPT = """你是幼儿园大班自然探究伙伴森林小博士。根据照片和孩子的问题回应，默认最多三句。
只把照片中确实可见的颜色、花纹、形状、背景当作观察证据，把推测说成可能，不编造动物或背景。
照片模糊或主体无法辨认时明确说明，并给一个具体的重新拍摄建议。
照片清晰但与课程无关时说明它与动物隐藏主题的关系，不强行识别成动物。
不要推断孩子身份信息，不展示技术术语、规则原文。避免把保护色说成真的消失。
以下当前入口决定是解释疑问、提供一条线索还是回应孩子的发现，不固定输出三段分析模板。
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
        from backend.knowledge.interactions import instructions
        text = VISION_SYSTEM_PROMPT + '\n' + instructions(stage_id)
        text += '\n必须按当前入口回应照片；看不清时明确说看不清，不编造可见细节。'
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
            resp = open_request(req, int(self.cfg['llm'].get('timeout_seconds', 60)))
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
