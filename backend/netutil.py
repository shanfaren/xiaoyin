# -*- coding: utf-8 -*-
"""局域网地址探测与连通性自检（标准库实现，不修改系统网络/安全设置）。"""
import socket
import urllib.error
import urllib.request


def primary_ip():
    """获取本机在局域网中的主 IPv4（通过 UDP 连接探测，不实际发包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def all_ipv4():
    """枚举本机所有 IPv4 地址（排除回环）。"""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:
        p = primary_ip()
        if p and not p.startswith('127.'):
            ips.add(p)
    except Exception:
        pass
    return sorted(i for i in ips if not i.startswith('127.'))


def candidate_urls(port, public_base_url=''):
    """给出候选访问地址（用于二维码与连通检测）。"""
    urls = []
    if public_base_url:
        urls.append({'url': public_base_url.rstrip('/') + '/scan', 'kind': 'public', 'label': '公网/正式域名'})
    for ip in all_ipv4():
        urls.append({'url': f'http://{ip}:{port}/scan', 'kind': 'lan', 'label': f'局域网 {ip}'})
    urls.append({'url': f'http://127.0.0.1:{port}/scan', 'kind': 'loopback',
                 'label': '本机（仅本机可访问，禁止用于学生二维码）'})
    return urls


def check_url(url, timeout=4):
    """对本机服务做一次 HTTP 连通检测。"""
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {'url': url, 'reachable': True, 'status': resp.status}
    except urllib.error.HTTPError as e:
        return {'url': url, 'reachable': True, 'status': e.code, 'note': '服务可达（返回非 200）'}
    except Exception as e:
        return {'url': url, 'reachable': False, 'error': f'{type(e).__name__}: {e}'}


def is_loopback(ip):
    return ip.startswith('127.') or ip in ('::1', 'localhost')


def is_private(ip):
    try:
        parts = [int(x) for x in ip.split('.')]
    except Exception:
        return False
    if len(parts) != 4:
        return False
    a, b = parts[0], parts[1]
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or a == 127
