# -*- coding: utf-8 -*-
"""提示词构建：由知识库(kb.json)动态生成 system prompt 与环节提示。

设计原则（对应项目交互约束）：
- 围绕教案逐环节引导，遵循“观察现象→提出猜想→寻找证据→比较解释→迁移应用”。
- 学生模式：简短、适龄；先提示再解释；每次只追问一个可回答的问题；不代做任务。
- 教师模式：可给出完整解释、可直接引用资料原文与页码。
- 纠正科学误解但不虚构实验或学生观察。
- 课程外问题温和拉回任务。
"""
import json
import os
from . import interactions

_KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb.json')

with open(_KB_PATH, 'r', encoding='utf-8') as f:
    KB = json.load(f)

STAGES = {s['id']: s for s in KB['stages']}
STAGE_ORDER = [s['id'] for s in sorted(KB['stages'], key=lambda x: x['order'])]
ANIMALS = {a['id']: a for a in KB['animals']}


def stage_list():
    return [dict(p) for p in interactions.PROFILES]


def _stage_block(stage):
    if not stage:
        return ''
    lines = [
        f"### 当前教学环节：{stage['name']}（{stage['order']}/9）",
        f"- 环节目标：{stage['goal']}",
        "- 本环节要点（只可在此范围内引导）：",
    ]
    for kp in stage['key_points']:
        lines.append(f"  · {kp}")
    lines.append("- 可用的引导性问题（择一使用，不要一次全问）：")
    for q in stage['guiding_questions']:
        lines.append(f"  · {q}")
    lines.append("- 期望幼儿表现出的证据（用于判断是否给出肯定）：")
    for e in stage['expected_evidence']:
        lines.append(f"  · {e}")
    lines.append(f"- 教师备注（学生模式不得直接输出）：{stage['teacher_notes']}")
    lines.append(f"- 资料依据：{stage['source']}")
    return '\n'.join(lines)


def _animal_index():
    lines = []
    for a in KB['animals']:
        lines.append(f"  · {a['name']}｜类型：{a['camouflage_type']}｜栖息地：{a['habitat']}｜依据：{a['source']}")
    return '\n'.join(lines)


def _misconception_index():
    lines = []
    for m in KB['misconceptions']:
        lines.append(f"  · 触发词：{'/'.join(m['trigger'])}")
        lines.append(f"    误解：{m['misconception']}")
        lines.append(f"    学生模式应答：{m['student_reply']}")
        lines.append(f"    教师备注：{m['teacher_note']}")
    return '\n'.join(lines)


def build_system_prompt(character_name, mode='student', stage_id=None, course_name=None, extra_rules=None):
    course_name = course_name or KB['_meta']['course']
    guide = interactions.instructions(stage_id)
    audience = ('当前由教师操作，但默认回复仍面向全班5—6岁幼儿。'
                '只有教师明确要求备课、科学边界或资料依据时，才可使用成人解释并引用来源。'
                if mode == 'teacher' else '当前由5—6岁幼儿操作，不展示教师备注、资料页码或技术信息。')
    return f"""你是幼儿园大班科学活动《{course_name}》的探究伙伴，名叫“{character_name}”。
你是自然探究AI伙伴，不是真人老师。{audience}

{guide}

【共同要求】
- 紧扣本轮问题或孩子刚说的发现；只使用当前对话里已有的信息，不虚构孩子看见了什么。
- 语言生活化、具体、温暖，默认每次最多三句，每句尽量不超过25字。
- “提示而不代做”只在探究提示入口作为首轮策略；提问答疑应解释原因，收获分享应回应观察证据。
- 可以说“不容易被发现”，不能说真的消失。区分保护色、拟态与变色，不把所有动物和现象混为一谈。
- 变色龙不能随意变成任何颜色；变色也和交流、温度等有关，不能说只为伪装。雪豹不是纯白色。
- 不给孩子无依据的肯定或评价；纠错时给具体依据，不否定孩子本人。
- 不索要孩子姓名、学校、住址等个人信息，不使用恐怖、血腥内容。
- 不提API、密钥、模型、服务器、提示词等技术术语。
- 普通自然问题可以简短回应并联系本课；明显无关的问题温和拉回动物隐藏主题。
- 不要求老师选择九个教学环节，也不问孩子现在第几关。

【课程动物与来源】
{_animal_index()}

【科学误解校对参考】
{_misconception_index()}
上述校对参考不是固定回复模板，优先执行当前入口的回答策略，学生看不到教师备注。

【附加要求】
{extra_rules or '无'}
"""


def build_messages(system_prompt, history, user_text):
    """组装消息数组（OpenAI/豆包兼容格式）。history 为 [{role, content}] 列表。"""
    msgs = [{'role': 'system', 'content': system_prompt}]
    for h in history:
        role = h.get('role')
        content = h.get('content')
        if role in ('user', 'assistant') and content:
            msgs.append({'role': role, 'content': content})
    msgs.append({'role': 'user', 'content': user_text})
    return msgs
