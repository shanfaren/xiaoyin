"""Local classroom mode can reach official Ark directly; TLS verification stays enabled."""
import os
import urllib.request
from urllib.parse import urlsplit

def open_request(request, timeout):
    host=urlsplit(request.full_url if hasattr(request,'full_url') else request).hostname
    if os.environ.get('FOREST_LOCAL_DESKTOP')=='1' and host=='ark.cn-beijing.volces.com':
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=timeout)
    return urllib.request.urlopen(request,timeout=timeout)
