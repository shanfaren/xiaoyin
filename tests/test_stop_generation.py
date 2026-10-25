# -*- coding: utf-8 -*-
"""专项测试：停止生成 / 打断。

验证内容：
- 生成过程中调用 POST /api/chat/stop 后，SSE 流提前结束，done 事件 stopped=True；
- 停止后会话不损坏，仍可继续发起新对话；
- 停止只影响目标会话（其他会话不受影响）。

运行：python tests/test_stop_generation.py --base http://127.0.0.1:8010
"""
import argparse
import json
import sys
import threading
import time
import urllib.request

sys.path.insert(0, __file__.rsplit('tests', 1)[0].rstrip('\\/'))
from tests.test_api import req, sse_chat  # noqa: E402


def sse_chat_with_stop(base, sid, text, stop_after_first_delta=True, stage_id='level1'):
    """发起 SSE 对话；一旦收到第一个 delta 就立即（同步）调用 stop 接口，
    然后继续读完整个流。返回 (events, answer_text, stop_was_sent)。"""
    body = {'session_id': sid, 'text': text, 'mode': 'student', 'stage_id': stage_id}
    url = base + '/api/chat'
    r = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                               headers={'Content-Type': 'application/json'}, method='POST')
    events, text_parts = [], []
    stop_was_sent = False

    with urllib.request.urlopen(r, timeout=60) as resp:
        buf = b''
        while True:
            chunk = resp.read(1)
            if not chunk:
                break
            buf += chunk
            if buf.endswith(b'\n\n'):
                for line in buf.decode('utf-8', 'ignore').split('\n'):
                    if not line.startswith('data: '):
                        continue
                    try:
                        ev = json.loads(line[6:])
                    except Exception:
                        continue
                    events.append(ev)
                    if ev.get('type') == 'delta':
                        text_parts.append(ev.get('text', ''))
                        if stop_after_first_delta and not stop_was_sent:
                            stop_was_sent = True
                            try:
                                req(base, 'POST', '/api/chat/stop', {'session_id': sid})
                            except Exception:
                                pass
                buf = b''

    return events, ''.join(text_parts), stop_was_sent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8010')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    results = []

    def record(name, ok, detail=''):
        results.append((name, ok, detail))
        print(('  [PASS] ' if ok else '  [FAIL] ') + name + (('  -> ' + str(detail)) if detail else ''))

    print('=' * 66)
    print(' 停止生成 / 打断测试 @', base)
    print('=' * 66)

    st, s, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sid = s['session_id']

    # 演示模式回答较短，重试若干次直到命中“生成中被停止”
    stopped_seen = False
    done_info = None
    for attempt in range(6):
        events, ans, _ = sse_chat_with_stop(base, sid, '请详细讲讲猫头鹰的隐身魔法，还有枯叶蝶和竹节虫的故事，越详细越好。')
        done = next((e for e in events if e.get('type') == 'done'), None)
        if done and done.get('stopped'):
            stopped_seen = True
            done_info = done
            break
    record('生成过程中调用 stop，done.stopped=True', stopped_seen,
           (done_info or {}).get('chars'))

    # 停止后会话仍可用
    events, ans = sse_chat(base, sid, '停止之后我还可以继续提问吗？')
    record('停止后会话仍可继续对话', bool(ans.strip()), ans[:40])
    done = next((e for e in events if e.get('type') == 'done'), None)
    record('停止后再次生成未被误停（stopped=False）',
           bool(done) and done.get('stopped') is False, done)

    # stop 只影响目标会话
    st, s2, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sid2 = s2['session_id']
    events2, ans2 = sse_chat(base, sid2, '另一个会话不受影响吧？')
    done2 = next((e for e in events2 if e.get('type') == 'done'), None)
    record('另一会话不受 stop 影响', bool(ans2.strip()) and (done2 or {}).get('stopped') is False,
           ans2[:40])

    ok_all = all(ok for _, ok, _ in results)
    print('\n 汇总：%d/%d 通过' % (sum(1 for _, ok, _ in results if ok), len(results)))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
