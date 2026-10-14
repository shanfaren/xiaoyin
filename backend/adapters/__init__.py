# -*- coding: utf-8 -*-
"""适配层包：模型 / 多模态 / 语音识别 / 语音合成。

所有适配器遵循同一约定：
- 未配置时抛出 NotConfigured，由上层转换为明确的“未配置”状态，绝不伪造成功。
- 全部使用标准库 urllib，无第三方依赖。
"""
from .errors import NotConfigured, UpstreamError, TimeoutError_, RateLimited

__all__ = ['NotConfigured', 'UpstreamError', 'TimeoutError_', 'RateLimited']
