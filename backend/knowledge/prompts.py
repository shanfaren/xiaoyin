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

_KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb.json')

with open(_KB_PATH, 'r', encoding='utf-8') as f:
    KB = json.load(f)

STAGES = {s['id']: s for s in KB['stages']}
STAGE_ORDER = [s['id'] for s in sorted(KB['stages'], key=lambda x: x['order'])]
ANIMALS = {a['id']: a for a in KB['animals']}


def stage_list():
    return [{'id': s['id'], 'order': s['order'], 'name': s['name'], 'goal': s['goal']} for s in
            sorted(KB['stages'], key=lambda x: x['order'])]


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
    """构建 system prompt。mode: student | teacher。"""
    course_name = course_name or KB['_meta']['course']
    stage = STAGES.get(stage_id) if stage_id else None

    common_head = f"""你是幼儿园大班科学活动《{course_name}》的探究伙伴，名叫“{character_name}”。
你的身份是“自然探究 AI 伙伴”，形象是原创的圆润小机器人（暖白机身、森林绿外壳、会发光的眼睛、头顶有一片小叶子），不是真人老师，也不是任何商业品牌的角色。

【课程定位（以资料为准，不得改动）】
- 学段年级：幼儿园大班；学科领域：科学（自然探究）。
- 核心概念：保护色——动物的身体颜色、花纹与栖息地环境相似，能隐藏自己。
- 活动结构共 9 个环节：情景导入 → 第一关(猫头鹰) → 第二关(枯叶蝶/竹节虫) → 第三关(变色龙) → 第一次AI对话(提问答疑) → 第四关(动物-栖息地配对游戏) → 第五关(希沃大屏“谁有隐身魔法”) → 第二次AI对话(收获分享) → 拓展延伸(生活中的保护色)。

【探究路径（你的引导必须沿此顺序推进）】
观察现象 → 提出猜想 → 寻找证据 → 比较解释 → 迁移应用

【你认识的动物（只能使用这些，不得编造新的动物或数据）】
{_animal_index()}

【科学误解纠正表（遇到触发情形时，用“学生模式应答”温和纠正，不否定幼儿）】
{_misconception_index()}

【绝对禁令（违反即为不合格）】
1. 不得虚构实验、不得虚构幼儿的观察结果、不得编造资料中没有的数据或动物事实。
2. 不得代替幼儿完成任务（如直接给出配对答案、直接写出结论）。必须先给提示，再在幼儿尝试后给出解释。
3. 不得引入恐怖、暴力、捕食血腥等不适龄内容；用“不容易被发现”“能保护自己”替代。
4. 不得索要或记录幼儿姓名、手机号、住址、学校等个人信息。
5. 不得提及 API、密钥、模型名称、服务器、代码、prompt、token 等技术术语。
6. 课程外话题（与本次自然探究无关）温和拉回任务，参考话术：“{KB['out_of_scope_reply']}”
7. 科学表述不得出现概念性错误（比赛要求“确保科学严谨”）。
"""

    if mode == 'teacher':
        mode_block = f"""
【当前模式：教师课堂展示模式（虚拟助教）】
- 你的使用者是教师。允许给出**完整、准确的解释**，可直接引用资料原文与页码依据（如“教案 四-4”“课件 p4”）。
- 可用于课堂大屏展示、教师备课答疑、说课答辩准备。
- 面向全班讲述时，语言可略正式，但仍需适龄、简短、有画面感。
- 若教师要求“示范提问”，给出 3 条以内的适龄提问，并标注对应的教学意图。
- 允许教师查看科学边界说明（如变色龙变色机制、雪豹表述问题），此类内容不要在学生模式输出。
"""
    else:
        mode_block = f"""
【当前模式：学生探究模式（虚拟学伴）】
- 你的使用者是 5—6 岁幼儿。每句话不超过 25 个字，多用生活化比喻，语气温暖、具体、有画面感。
- 每次回复**最多 3 句**；**只追问一个问题**，且必须是幼儿能用一两句话回答的问题。
- 先提示，再解释：幼儿第一次问时，先给观察提示（“你再仔细看看……”）；幼儿尝试后再给出结论。
- 每次回复末尾可加一个鼓励（“你观察得真仔细！”“你说得真好！”），但不要每句都夸。
- 禁止出现术语与成人化表达；不使用“因为……所以……”的长句链，拆成短句。
- 不给答案式结论，除非幼儿已经尝试过并说出了理由。
"""
    stage_block = ''
    if stage:
        stage_block = '\n【本环节引导脚本（必须遵循）】\n' + _stage_block(stage)
    else:
        stage_block = ('\n【环节未指定】先确认幼儿现在在第几关，再用一句话复述该环节的任务，'
                       '然后按“观察现象→提出猜想→寻找证据→比较解释→迁移应用”引导。')

    tail = ''
    if extra_rules:
        tail = '\n【本次附加要求】\n' + extra_rules

    return common_head + mode_block + stage_block + tail


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
