# -*- coding: utf-8 -*-
"""专项测试：中文输入/输出编码与适龄表达（演示模式）。"""
import sys

sys.path.insert(0, __file__.rsplit('tests', 1)[0].rstrip('\\/'))
from tests.test_api import req, sse_chat  # noqa: E402


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8010'
    results = []

    def record(name, ok, detail=''):
        results.append((name, bool(ok)))
        print(('  [PASS] ' if ok else '  [FAIL] ') + name + (('  -> ' + str(detail)) if detail else ''))

    print('=' * 66)
    print(' 中文输入/输出与适龄表达测试 @', base)
    print('=' * 66)

    st, s, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sid = s['session_id']

    q = '变色龙为什么会变色？它想变什么颜色都行吗？'
    ev, ans = sse_chat(base, sid, q, stage_id='level3')
    cjk = sum(1 for ch in ans if '\u4e00' <= ch <= '\u9fff')
    record('中文提问返回中文回答（CJK 字符占比高）', cjk >= max(5, len(ans) * 0.3),
           f'len={len(ans)} cjk={cjk}')
    record('无 UTF-8 乱码（Ã/ï¼ 特征串）', ('Ã' not in ans) and ('ï¼' not in ans), ans[:40])
    record('演示模式明确标注“非真实 AI”', ('演示' in ans and '非真实' in ans))
    # 断言只看“误区纠正话术”本身，不依赖随机尾句（避免不稳定断言）
    record('“变色龙可任意变色”误区被温和纠正',
           '跟着身边的地方慢慢变' in ans, ans.replace('\n', ' ')[:70])

    # 更直接地触发“任意变色”说法，验证纠正话术稳定生效
    st, s3, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    ev3, ans3 = sse_chat(base, s3['session_id'], '变色龙想变什么颜色就变什么颜色，对吗？', stage_id='level3')
    record('明确“任意变色”说法被纠正为“跟着环境慢慢变”',
           '慢慢变' in ans3 and '跟着身边' in ans3, ans3.replace('\n', ' ')[:70])
    record('SSE 事件含中文字段且完整解析', any(e.get('type') == 'done' for e in ev))

    st, s2, _ = req(base, 'POST', '/api/session', {'mode': 'student'})
    sid2 = s2['session_id']
    q2 = '军人叔叔的迷彩服有什么用呀？'
    ev2, ans2 = sse_chat(base, sid2, q2, stage_id='extension')
    record('拓展环节（迷彩服）正常回答', ('迷彩' in ans2) and len(ans2) > 10, ans2[:50])

    print('\n 汇总：%d/%d 通过' % (sum(1 for _, ok in results if ok), len(results)))
    return 0 if all(ok for _, ok in results) else 1


if __name__ == '__main__':
    sys.exit(main())
