"""森林小博士的唯一声音规范：课堂、手机和视频配音共用。"""
VOICE_ID = 'zh_male_taocheng_uranus_bigtts'
SPEECH_RATE = -5
STYLE = '请用清爽、明亮、亲切的年轻男声自然说话，像陪孩子探索森林的小伙伴。吐字清楚，语气轻快温和，避免低沉播音腔和夸张表演。'
STANDARD_TEXT = '小朋友们好，我是森林小博士。让我们仔细观察，一起寻找动物的隐身秘密吧！'
PROFILE_ID = 'forest-doctor-male-v1'


def fixed_settings():
    return dict(provider='volcengine_seedtts', model='seed-tts-2.0',
                resource_id='seed-tts-2.0', voice=VOICE_ID,
                speech_rate=SPEECH_RATE, context_texts=[STYLE])


def public_profile():
    return dict(profile_id=PROFILE_ID, **fixed_settings(),
                sample_rate=16000, format='mp3', standard_text=STANDARD_TEXT)
