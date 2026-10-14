# -*- coding: utf-8 -*-
"""适配层异常定义。"""


class NotConfigured(Exception):
    """能力未配置（缺密钥/缺模型名/缺供应商）。上层据此返回明确的未配置状态。"""
    def __init__(self, capability, message):
        self.capability = capability
        self.message = message
        super().__init__(f'[{capability}] {message}')


class UpstreamError(Exception):
    """上游服务错误（含 HTTP 状态码）。"""
    def __init__(self, message, status=None, body=None):
        self.status = status
        self.body = body
        super().__init__(message)


class TimeoutError_(Exception):
    """上游超时。"""


class RateLimited(Exception):
    """本地限流命中。"""
