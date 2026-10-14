# -*- coding: utf-8 -*-
"""演示模式应答器（规则化，非真实 AI）。

用途：在**未配置任何模型密钥**时，让教师可以完整走通 UI 与接口流程做验收测试。
硬性要求：所有输出必须带明确标注，绝不可当作真实大模型效果呈现。
"""
import random

from .prompts import KB, STAGES, STAGE_ORDER

LABEL = '【演示模式·规则回答，非真实 AI】'


def _find_animal(text):
    for a in KB['animals']:
        if a['name'] in text:
            return a
    # 常见别名
    alias = {
        '猫头鹰': 'owl', '鸮': 'owl',
        '枯叶蝶': 'dead_leaf_butterfly', '蝴蝶': 'dead_leaf_butterfly',
        '竹节虫': 'stick_insect',
        '变色龙': 'chameleon',
        '蚱蜢': 'grasshopper', '蝗虫': 'grasshopper',
        '雪兔': 'snow_hare', '兔子': 'snow_hare',
        '北极熊': 'polar_bear',
        '兰花螳螂': 'orchid_mantis', '螳螂': 'orchid_mantis',
        '火烈鸟': 'flamingo',
        '孔雀': 'peacock',
        '鹦鹉': 'parrot',
        '金丝猴': 'golden_monkey',
        '迷彩服': 'camo_uniform', '迷彩': 'camo_uniform',
    }
    for k, vid in alias.items():
        if k in text:
            for a in KB['animals']:
                if a['id'] == vid:
                    return a
    return None


def _check_misconception(text):
    for m in KB['misconceptions']:
        for t in m['trigger']:
            if t in text:
                return m
    return None


def _animal_reply(a, mode):
    """按动物条目生成回答（学生模式：适龄表述 + 只追问一个问题）。"""
    if mode == 'teacher':
        return (f"{LABEL}\n【教师模式·完整说明】{a['name']}（{a['camouflage_type']}）\n"
                f"适龄表述：{a['child_talk']}\n可引导观察：{'、'.join(a['evidence_to_observe'])}\n"
                f"栖息地：{a['habitat']}\n科学说明：{a['adult_note']}\n资料依据：{a['source']}")
    tail = random.choice(['你再仔细看看，它身上有什么和周围很像的地方？',
                          '你猜猜，它为什么要这样藏起来呢？',
                          '它的家在哪里呀？'])
    return f"{LABEL}\n{a['child_talk']}\n{tail}"


def respond(messages, mode='student', stage_id=None):
    """messages: OpenAI 风格消息数组；取最后一条 user 内容做规则匹配。"""
    user_text = ''
    for m in reversed(messages):
        if m.get('role') == 'user':
            user_text = str(m.get('content') or '')
            break
    text = user_text.strip()

    if not text:
        return LABEL + '我听到啦，可是没有听清，你能再说一次吗？'

    # 1) 科学误解优先（触发词已在知识库中收紧，避免误伤正常提问）
    m = _check_misconception(text)
    if m:
        body = m['student_reply']
        if mode == 'teacher':
            return f"{LABEL}\n【教师模式·完整说明】{m['misconception']}\n建议应对：{body}\n教师备注：{m['teacher_note']}"
        return f'{LABEL}\n{body}'

    # 2) 动物识别
    a = _find_animal(text)
    if a:
        return _animal_reply(a, mode)

    # 3) 环节相关
    if stage_id and stage_id in STAGES:
        st = STAGES[stage_id]
        if mode == 'teacher':
            return (f"{LABEL}\n【教师模式·环节说明】{st['name']}\n环节目标：{st['goal']}\n"
                    f"要点：{'；'.join(st['key_points'])}\n教师备注：{st['teacher_notes']}\n资料依据：{st['source']}")
        q = st['guiding_questions'][0]
        return f"{LABEL}\n我们现在是“{st['name']}”。{q}"

    # 4) 兜底：课程外温和拉回
    if mode == 'teacher':
        return (f"{LABEL}\n【教师模式】该问题超出本课范围。本课为幼儿园大班科学《{KB['_meta']['course']}》，"
                f"核心概念是保护色。可用的 9 个环节：{' / '.join(s['name'] for s in KB['stages'])}。\n"
                f"建议：请教师端配置真实模型密钥后获得开放域问答能力。")
    return f"{LABEL}\n{KB['out_of_scope_reply']}"


def demo_note():
    return ('本回答由「演示模式」的课程知识库规则生成，**不是真实大模型输出**。'
            '请勿在比赛材料中将其作为 AI 效果展示；配置密钥后自动切换为真实模型。')
