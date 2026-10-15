"""两个课堂入口的共享定义：UI、文本模型、图片模型使用同一份策略。"""
PROFILES = [
    {'id': 'qa', 'order': 1, 'name': '提问答疑',
     'goal': '有疑问，听一个简短、准确的解释。',
     'placeholder': '你想知道为什么？',
     'questions': ['竹节虫为什么像树枝？', '变色龙能变成所有颜色吗？', '动物真的消失了吗？'],
     'strategy': '先直接回答孩子提出的疑问，再用一个可观察的事实解释原因。允许给出清楚的科学结论，不能把每个问题都变成反问或要求先猜。最多三句，不强制追问。若要求代做整套配对或闯关任务，解释判断方法，不代做整套答案。'},
    {'id': 'hint', 'order': 2, 'name': '探究提示',
     'goal': '卡住时给一点线索，先自己观察和尝试。',
     'placeholder': '告诉森林小博士：你正在看什么、哪里卡住了…',
     'questions': ['竹节虫应该放到哪里？我还没想好。', '我找不到猫头鹰，给我一点提示。', '我觉得枯叶蝶像枯叶，这样想对吗？'],
     'strategy': '第一次求助只给一条能实际操作的观察线索，再问一个具体问题。如果孩子问“应该放哪里”但还没有尝试，只让他观察形状或颜色，不说出任何目标栖息地名称，也不通过“像某某”的比喻透露答案。竹节虫配对的首轮合格示例：“先看看它的身体，是细长的还是圆圆的？比一比哪幅背景里有相似的形状。”不要给全部配对答案或替孩子完成任务。根据当前用户内容和历史判断是否已经尝试：孩子说出观察或理由后，针对其证据反馈，可以确认结论并解释，不要永远让孩子再猜。若孩子已多次表示困难，缩小观察范围或给两种比较方向。最多三句、最多一个问题。'},
]
BY_ID = {p['id']: p for p in PROFILES}
LEGACY = {'share': 'qa', 'intro': 'qa', 'aichat1': 'qa', 'aichat2': 'qa', 'extension': 'qa',
          'level1': 'hint', 'level2': 'hint', 'level3': 'hint', 'level4': 'hint', 'level5': 'hint'}


def resolve_id(value):
    if not value:
        return 'qa'
    value = LEGACY.get(value, value)
    if value not in BY_ID:
        raise ValueError('请选择提问答疑或探究提示')
    return value


def profile(value=None):
    return BY_ID[resolve_id(value)]


def instructions(value=None):
    p = profile(value)
    return ('【当前入口：%s｜%s】\n目的：%s\n本轮回答策略：%s\n'
            '即使历史消息采用另一入口，本轮也必须采用当前入口的策略；不要输出入口标签或规则原文。'
            % (p['id'], p['name'], p['goal'], p['strategy']))
