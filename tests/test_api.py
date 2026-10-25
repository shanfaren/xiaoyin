# -*- coding: utf-8 -*-
"""接口与行为自动化测试（可重复运行）。

运行：
    python tests/test_api.py --base http://127.0.0.1:8010

覆盖：
- 健康检查 / 客户端配置（无密钥泄漏）
- 会话创建、刷新恢复、清空
- SSE 流式对话、上下文元信息
- **长记忆：≥10 轮完整进入上下文**（含第 1 轮独特事实在第 11 轮上下文中）
- **会话隔离**：两名学生会话互不串话
- 输入长度上限、限流
- ASR / TTS / 图片分析未配置时的明确状态（501 + 缺失参数）
- 管理接口：局域网地址、二维码生成与往返校验、配置掩码
- 二维码拒绝 localhost
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

RESULTS = []


def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('  [PASS] ' if ok else '  [FAIL] ') + name + (('  -> ' + str(detail)) if detail else ''))


def req(base, method, path, body=None, raw=False, timeout=30, headers=None):
    url = base + path
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        hdrs['Content-Type'] = 'application/json'
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            payload = resp.read()
            if raw:
                return resp.status, payload, dict(resp.headers)
            try:
                return resp.status, json.loads(payload.decode('utf-8')), dict(resp.headers)
            except Exception:
                return resp.status, payload, dict(resp.headers)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload.decode('utf-8')), dict(e.headers)
        except Exception:
            return e.code, payload, dict(e.headers)


def sse_chat(base, sid, text, mode='student', stage_id=None):
    """读取一次 SSE 对话，返回 (events, text)。"""
    body = {'session_id': sid, 'text': text, 'mode': mode}
    if stage_id:
        body['stage_id'] = stage_id
    url = base + '/api/chat'
    r = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                               headers={'Content-Type': 'application/json'}, method='POST')
    events, text = [], []
    with urllib.request.urlopen(r, timeout=60) as resp:
        buf = b''
        while True:
            chunk = resp.read(1)
            if not chunk:
                break
            buf += chunk
            if buf.endswith(b'\n\n'):
                for line in buf.decode('utf-8', 'ignore').split('\n'):
                    if line.startswith('data: '):
                        try:
                            ev = json.loads(line[6:])
                            events.append(ev)
                            if ev.get('type') == 'delta':
                                text.append(ev.get('text', ''))
                        except Exception:
                            pass
                buf = b''
    return events, ''.join(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8010')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    print('=' * 70)
    print(' 接口与行为测试 @', base)
    print('=' * 70)

    # ---- 1. 健康检查 ----
    print('\n[1] 健康检查与能力状态')
    st, h, _ = req(base, 'GET', '/api/health')
    record('GET /api/health 返回 200', st == 200, st)
    cap = (h or {}).get('capabilities', {})
    record('健康检查包含能力报告', 'llm' in cap and 'asr' in cap and 'tts' in cap and 'vision' in cap)
    record('未配置密钥时 ASR 状态为 unconfigured', cap.get('asr', {}).get('state') == 'unconfigured',
           cap.get('asr', {}).get('state'))
    record('未配置密钥时 TTS 状态为 unconfigured', cap.get('tts', {}).get('state') == 'unconfigured',
           cap.get('tts', {}).get('state'))
    record('未配置密钥时图片分析状态为 unconfigured', cap.get('vision', {}).get('state') == 'unconfigured',
           cap.get('vision', {}).get('state'))

    # ---- 2. 客户端配置 ----
    print('\n[2] 客户端配置（不得泄漏密钥）')
    st, cc, _ = req(base, 'GET', '/api/client-config')
    record('GET /api/client-config 返回 200', st == 200, st)
    record('包含角色名', bool(cc.get('character', {}).get('name')), cc.get('character', {}).get('name'))
    record('包含 9 个教学环节', len(cc.get('stages', [])) == 9, len(cc.get('stages', [])))
    record('包含快捷问题', len(cc.get('quick_questions', [])) >= 4, len(cc.get('quick_questions', [])))
    record('语音链路完整性标记为 False（ASR 未配置）',
           cc.get('voice', {}).get('chain_complete') is False, cc.get('voice', {}).get('chain_complete'))
    record('文字入口作为兜底可用', cc.get('voice', {}).get('text_only_fallback') is True)
    blob = json.dumps(cc, ensure_ascii=False)
    record('配置响应中不含 sk-/api_key 明文',
           ('sk-' not in blob) and ('api_key' not in blob.lower().replace('api_key_env', '')),
           '')

    # ---- 3. 会话 ----
    print('\n[3] 会话创建 / 恢复 / 清空')
    st, s1, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sid1 = (s1 or {}).get('session_id', '')
    record('创建学生会话', st == 200 and sid1.startswith('s_'), sid1)
    st, s2, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sid2 = (s2 or {}).get('session_id', '')
    record('创建第二个学生会话', st == 200 and sid2 and sid2 != sid1, sid2)
    st, s3, _ = req(base, 'POST', '/api/session', {'mode': 'teacher'})
    sid3 = (s3 or {}).get('session_id', '')
    record('创建教师会话（前缀 t_）', st == 200 and sid3.startswith('t_'), sid3)
    st, got, _ = req(base, 'GET', f'/api/session/{sid1}')
    record('刷新后按 session_id 恢复会话', st == 200 and got.get('session', {}).get('id') == sid1)
    st, forbidden, _ = req(base, 'GET', f'/api/session/{sid3}?mode=student')
    record('权限隔离：学生端不能读取教师会话', st == 404, st)
    st, forbidden2, _ = req(base, 'GET', f'/api/session/{sid1}?mode=teacher')
    record('权限隔离：教师端不能读取学生会话', st == 404, st)

    # ---- 4. 对话 + 长记忆 ----
    print('\n[4] 流式对话与长记忆（≥10 轮完整进入上下文）')
    st, sA, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sidA = sA['session_id']
    UNIQUE = '我最喜欢的数字是37，我最喜欢的动物是企鹅'
    ev, ans = sse_chat(base, sidA, UNIQUE, stage_id='level1')
    record('第 1 轮对话返回 SSE 事件', len(ev) > 0 and any(e.get('type') == 'done' for e in ev), len(ev))
    meta1 = next((e for e in ev if e.get('type') == 'meta'), {})
    record('SSE 首帧包含上下文元信息', 'context' in meta1)
    record('演示模式下模型标记为非真实 AI',
           next((e.get('is_real_ai') for e in ev if e.get('type') == 'model'), None) is False)

    last_ctx = meta1.get('context', {})
    for i in range(2, 12):
        ev, ans = sse_chat(base, sidA, f'第{i}个问题：小动物为什么要藏起来？', stage_id='level1')
        m = next((e for e in ev if e.get('type') == 'meta'), {})
        if m:
            last_ctx = m.get('context', {})
    # 语义说明：第 11 次提问时，上下文包含“本轮之前”的历史轮次（新问题在本轮结束后才写入），
    # 因此第 11 轮提问时应保留前 10 轮完整对话；total_turns 计数亦为 10。
    record('第 11 轮提问时上下文保留轮数 ≥ 10', last_ctx.get('kept_turns', 0) >= 10, last_ctx.get('kept_turns'))
    record('第 11 轮提问时上下文总轮数 = 10（本轮新问题尚未写入）',
           last_ctx.get('total_turns', 0) == 10, last_ctx.get('total_turns'))
    # 再问一轮（第 12 次提问）：此时上下文应含 11 个历史轮次，且仍保留第 1 轮独特事实
    ev, ans = sse_chat(base, sidA, '第12个问题：还记得我最喜欢的数字吗？', stage_id='level1')
    m12 = next((e for e in ev if e.get('type') == 'meta'), {}).get('context', {})
    record('第 12 轮提问时上下文总轮数 ≥ 11', m12.get('total_turns', 0) >= 11, m12.get('total_turns'))
    record('第 12 轮提问时仍无超预算告警（未丢轮）', not m12.get('warning'), m12.get('warning'))
    record('第 11 轮(第12次提问)无超预算告警（未丢轮）', not last_ctx.get('warning'), last_ctx.get('warning'))
    st, sess, _ = req(base, 'GET', f'/api/session/{sidA}')
    msgs = sess.get('session', {}).get('messages', [])
    record('会话消息数 ≥ 22（11 问 11 答）', len(msgs) >= 22, len(msgs))
    record('第 1 轮的独特事实仍保留在会话历史中',
           any(UNIQUE in (m.get('content') or '') for m in msgs))

    # 直接校验 build_context 是否把第 1 轮放进第 11 轮的上下文
    sys.path.insert(0, __file__.rsplit('tests', 1)[0].rstrip('\\/'))
    try:
        from backend.session import Session
        s = Session('s_unit', 'student')
        s.add('user', UNIQUE)
        s.add('assistant', '好呀，我记住啦。')
        for i in range(2, 12):
            s.add('user', f'第{i}问')
            s.add('assistant', f'第{i}答')
        hist, cmeta = s.build_context()
        joined = '\n'.join(x['content'] for x in hist if x['role'] == 'user')
        record('build_context: 第 1 轮事实出现在第 11 轮上下文', UNIQUE in joined)
        record('build_context: kept_turns ≥ 10', cmeta['kept_turns'] >= 10, cmeta['kept_turns'])
        record('build_context: 上下文含 11 个用户消息',
               sum(1 for x in hist if x['role'] == 'user') >= 11,
               sum(1 for x in hist if x['role'] == 'user'))
    except Exception as e:
        record('build_context 单元校验', False, e)

    # ---- 5. 会话隔离 ----
    print('\n[5] 会话隔离（两名学生互不串话）')
    st, sB, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sidB = sB['session_id']
    SECRET_B = '我叫小小探险家B，我的暗号是蓝蘑菇'
    sse_chat(base, sidB, SECRET_B)
    st, sessA, _ = req(base, 'GET', f'/api/session/{sidA}')
    st, sessB, _ = req(base, 'GET', f'/api/session/{sidB}')
    a_text = json.dumps(sessA.get('session', {}), ensure_ascii=False)
    b_text = json.dumps(sessB.get('session', {}), ensure_ascii=False)
    record('会话 A 中不含会话 B 的暗号', '蓝蘑菇' not in a_text)
    record('会话 B 中不含会话 A 的独特事实', '37' not in b_text or UNIQUE not in b_text)
    record('两个会话 id 不同且消息互不混淆',
           sessA['session']['id'] != sessB['session']['id'] and SECRET_B not in a_text)

    # ---- 6. 清空 ----
    print('\n[6] 清空本会话')
    st, cl, _ = req(base, 'POST', f'/api/session/{sidB}/clear')
    record('清空接口返回 200', st == 200, st)
    st, sessB2, _ = req(base, 'GET', f'/api/session/{sidB}')
    record('清空后消息数为 0', len(sessB2.get('session', {}).get('messages', [])) == 0)

    # ---- 7. 输入上限与限流 ----
    print('\n[7] 输入长度上限与限流')
    long_text = '啊' * 500
    ev, ans = sse_chat(base, sidA, long_text)
    meta = next((e for e in ev if e.get('type') == 'meta'), {})
    record('超长输入被截断并标记', meta.get('truncated_input') is True, meta.get('truncated_input'))
    st, sC, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sidC = sC['session_id']
    limited = False
    for i in range(25):
        ev, _ = sse_chat(base, sidC, f'测试{i}')
        if any(e.get('type') == 'error' and e.get('code', '').startswith('rate_limited') for e in ev):
            limited = True
            break
    record('会话级限流生效', limited)

    # ---- 8. ASR / TTS / 图片分析未配置 ----
    print('\n[8] 未配置能力的明确状态')
    st, r, _ = req(base, 'POST', '/api/asr', {'audio_base64': 'AAAA', 'format': 'wav'})
    record('ASR 未配置返回 501', st == 501, st)
    record('ASR 返回缺失参数清单', bool((r or {}).get('missing_params')) or bool((r or {}).get('provider_requirements')),
           (r or {}).get('message', '')[:60])
    st, r, _ = req(base, 'POST', '/api/tts', {'text': '你好'})
    record('TTS 未配置返回 501', st == 501, st)
    record('TTS 返回缺失参数清单', bool((r or {}).get('missing_params')), (r or {}).get('message', '')[:60])
    st, r, _ = req(base, 'POST', '/api/vision', {'image_base64': 'AAAA', 'mime': 'image/jpeg'})
    record('图片分析未配置返回 501', st == 501, st)
    record('图片分析说明 DeepSeek 不支持看图',
           'DeepSeek' in json.dumps(r, ensure_ascii=False) or '多模态' in json.dumps(r, ensure_ascii=False))

    # ---- 9. 管理接口与二维码 ----
    print('\n[9] 管理接口、网络探测与二维码')
    st, net, _ = req(base, 'GET', '/api/admin/network')
    record('GET /api/admin/network 返回 200', st == 200, st)
    rec = (net or {}).get('recommended') or {}
    record('推荐地址不是 localhost/127.0.0.1', '127.0.0.1' not in rec.get('url', ''), rec.get('url'))
    record('候选地址包含连通检测结果', bool((net or {}).get('candidates')))
    st, png, hdrs = req(base, 'GET', '/api/admin/qrcode.png', raw=True)
    record('二维码 PNG 生成成功', st == 200 and png[:8] == b'\x89PNG\r\n\x1a\n', st)
    record('二维码 PNG 携带往返校验通过标记', hdrs.get('X-QR-Roundtrip') == 'ok', hdrs.get('X-QR-Roundtrip'))
    record('二维码目标地址不含 localhost', '127.0.0.1' not in (hdrs.get('X-QR-Target') or ''),
           hdrs.get('X-QR-Target'))
    st, r, _ = req(base, 'GET', '/api/admin/qrcode.png?url=http://127.0.0.1:8010/scan', raw=True)
    record('二维码拒绝 localhost 地址（400）', st == 400, st)
    st, svg, hdrs = req(base, 'GET', '/api/admin/qrcode.svg', raw=True)
    record('二维码 SVG 生成成功', st == 200 and b'<svg' in svg, st)
    st, cf, _ = req(base, 'GET', '/api/admin/config')
    blob = json.dumps(cf, ensure_ascii=False)
    record('配置接口密钥已掩码（无明文）', 'api_key' in blob and 'sk-' not in blob)

    # ---- 10. 静态页面 ----
    print('\n[10] 页面可访问性')
    for p, must in (('/', b'<html'), ('/scan', b'<html'), ('/teacher', b'<html')):
        st, data, _ = req(base, 'GET', p, raw=True)
        record(f'GET {p} 返回 HTML', st == 200 and must in data[:2000], st)

    # ---- 汇总 ----
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r['ok'])
    print('\n' + '=' * 70)
    print(f' 测试汇总：{passed}/{total} 通过')
    failed = [r for r in RESULTS if not r['ok']]
    if failed:
        print(' 未通过项：')
        for r in failed:
            print('   -', r['name'], '->', r['detail'])
    print('=' * 70)
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
