# -*- coding: utf-8 -*-
"""配置加载：config/config.json（本地私密，不入库）+ 环境变量覆盖。

安全要求：
- 密钥只保存在教师 PC 的本地私密配置或环境变量中；
- 不写入网页、二维码、导出物或日志；
- 本模块提供 redact() 用于日志脱敏；对外接口只返回“是否已配置”，绝不返回密钥。
"""
import copy
import json
import os
from .voice_profile import fixed_settings, public_profile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
EXAMPLE_PATH = os.path.join(CONFIG_DIR, 'config.example.json')

DEFAULTS = {
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        "public_base_url": "",
        "allow_cors_origins": [],
        "trust_proxy_headers": False,
        "admin_token": ""
    },
    "character": {
        "name": "森林小博士",
        "alias": "AI自然探究伙伴",
        "course_name": "解锁大自然的隐身魔法",
        "welcome": "你好呀！我是森林小博士，你的自然探究小伙伴。今天我们一起走进大森林，去找会隐身的小动物吧！"
    },
    "llm": {
        "primary": {
            "provider": "doubao",
            "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
            "model": "",
            "endpoint_id": "",
            "api_key": "",
            "api_key_env": "ARK_API_KEY"
        },
        "fallback": {
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "api_key": "",
            "api_key_env": "DEEPSEEK_API_KEY"
        },
        "timeout_seconds": 60,
        "max_retries": 2,
        "stream": True,
        "thinking_disabled": True,
        "temperature": 0.6,
        "max_tokens": 512
    },
    "vision": {
        "provider": "doubao",
        "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "model": "",
        "api_key": "",
        "api_key_env": "ARK_API_KEY",
        "enabled": False
    },
    "image_search": {
        "provider": "doubao_custom",
        "base_url": "https://open.feedcoopapi.com",
        "api_key": "",
        "api_key_env": "DOUBAO_SEARCH_API_KEY",
        "enabled": False,
        "count": 6,
        "timeout_seconds": 10
    },
    "asr": {
        "provider": "ark_audio",
        "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "model": "doubao-seed-2-1-lite-260915",
        "credential_source": "llm.primary",
        "api_key": "",
        "api_key_env": "ASR_API_KEY",
        "app_id": "",
        "app_id_env": "ASR_APP_ID",
        "enabled": False
    },
    "streaming_asr": {
        "enabled": False,
        "base_url": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
        "resource_id": "volc.seedasr.sauc.duration",
        "api_key": "",
        "app_id": ""
    },
    "tts": {
        "provider": "volcengine_seedtts",
        "base_url": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        "model": "seed-tts-2.0",
        "resource_id": "seed-tts-2.0",
        "api_key": "",
        "api_key_env": "TTS_API_KEY",
        "voice": "zh_male_taocheng_uranus_bigtts",
        "speech_rate": -5,
        "context_texts": ["请用清爽、明亮、亲切的年轻男声自然说话，像陪孩子探索森林的小伙伴。吐字清楚，语气轻快温和，避免低沉播音腔和夸张表演。"],
        "enabled": False
    },
    "limits": {
        "max_input_chars": 300,
        "max_image_mb": 5,
        "rate_per_minute_per_session": 20,
        "rate_per_minute_global": 300,
        "max_history_turns": 40,
        "min_keep_turns": 10,
        "context_token_budget": 6000,
        "session_ttl_hours": 12,
        "max_image_refs": 5
    },
    "modes": {
        "demo": False,
        "demo_label": "演示模式（非真实 AI，使用课程知识库固定规则回答）"
    }
}

_SECRET_PATHS = [
    ('llm', 'primary', 'api_key'), ('llm', 'fallback', 'api_key'),
    ('vision', 'api_key'), ('asr', 'api_key'), ('tts', 'api_key'),
    ('image_search', 'api_key'),
]


def _deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env_override(cfg):
    """环境变量优先于配置文件（部署时用环境变量注入密钥）。"""
    env_map = {
        ('server', 'host'): 'APP_HOST',
        ('server', 'port'): 'APP_PORT',
        ('server', 'public_base_url'): 'APP_PUBLIC_BASE_URL',
        ('character', 'name'): 'APP_CHARACTER_NAME',
        ('llm', 'primary', 'api_key'): 'ARK_API_KEY',
        ('llm', 'primary', 'model'): 'ARK_MODEL',
        ('llm', 'primary', 'endpoint_id'): 'ARK_ENDPOINT_ID',
        ('llm', 'fallback', 'api_key'): 'DEEPSEEK_API_KEY',
        ('llm', 'fallback', 'model'): 'DEEPSEEK_MODEL',
        ('vision', 'api_key'): 'ARK_API_KEY',
        ('vision', 'model'): 'ARK_VISION_MODEL',
        ('image_search', 'api_key'): 'DOUBAO_SEARCH_API_KEY',
        ('image_search', 'base_url'): 'DOUBAO_SEARCH_BASE_URL',
        ('asr', 'provider'): 'ASR_PROVIDER',
        ('asr', 'base_url'): 'ASR_BASE_URL',
        ('asr', 'model'): 'ASR_MODEL',
        ('asr', 'credential_source'): 'ASR_CREDENTIAL_SOURCE',
        ('asr', 'api_key'): 'ASR_API_KEY',
        ('asr', 'app_id'): 'ASR_APP_ID',
        ('asr', 'resource_id'): 'ASR_RESOURCE_ID',
        ('streaming_asr', 'enabled'): 'STREAMING_ASR_ENABLED',
        ('streaming_asr', 'base_url'): 'STREAMING_ASR_BASE_URL',
        ('streaming_asr', 'resource_id'): 'STREAMING_ASR_RESOURCE_ID',
        ('streaming_asr', 'api_key'): 'STREAMING_ASR_API_KEY',
        ('streaming_asr', 'app_id'): 'STREAMING_ASR_APP_ID',
        ('tts', 'api_key'): 'TTS_API_KEY',
        ('tts', 'voice'): 'TTS_VOICE',
    }
    for path, env in env_map.items():
        val = os.environ.get(env)
        if val:
            node = cfg
            for p in path[:-1]:
                node = node.setdefault(p, {})
            node[path[-1]] = int(val) if (path[-1] == 'port' and str(val).isdigit()) else val
    # 云端托管平台（Render 等）通过反向代理注入 X-Forwarded-*，
    # 需信任代理头才能识别公网域名（让二维码/接入信息自动指向公网地址）。
    _trust = os.environ.get('APP_TRUST_PROXY_HEADERS', '').lower() in ('1', 'true', 'yes')
    if _trust or os.environ.get('RENDER') or os.environ.get('RENDER_SERVICE_ID'):
        cfg['server']['trust_proxy_headers'] = True
    if os.environ.get('APP_DEMO_MODE', '').lower() in ('1', 'true', 'yes'):
        cfg['modes']['demo'] = True
    if os.environ.get('APP_CORS_ORIGINS'):
        cfg['server']['allow_cors_origins'] = [o.strip() for o in os.environ['APP_CORS_ORIGINS'].split(',') if o.strip()]

    # 云端仅注入密钥时，自动把“具备完整参数 + 有密钥”的能力置为启用；
    # 本地无密钥时保持 enabled=False，界面继续显示“未配置”。
    vis = cfg['vision']
    if str(vis.get('api_key') or '').strip() and str(vis.get('base_url') or '').strip() and vis.get('model'):
        vis['enabled'] = True
    ims = cfg['image_search']
    if str(ims.get('api_key') or '').strip() and str(ims.get('base_url') or '').strip():
        ims['enabled'] = True
    tts = cfg['tts']
    # 音色属于角色身份；历史文件、环境变量和单次请求均不能改换它。
    tts.update(fixed_settings())
    if (tts.get('provider') == 'volcengine_seedtts' and str(tts.get('api_key') or '').strip()
            and str(tts.get('voice') or '').strip() and str(tts.get('base_url') or '').strip()):
        tts['enabled'] = True
    asr = cfg['asr']
    if asr.get('credential_source') == 'llm.primary' and not str(asr.get('api_key') or '').strip():
        asr['api_key'] = cfg['llm']['primary'].get('api_key', '')
        if not asr.get('base_url'):
            asr['base_url'] = cfg['llm']['primary'].get('base_url', '')
    if str(asr.get('api_key') or '').strip() and str(asr.get('base_url') or '').strip():
        asr['enabled'] = True
    return cfg


def load_config():
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = _deep_merge(cfg, json.load(f))
        except Exception as e:
            raise RuntimeError(f'配置文件解析失败 {CONFIG_PATH}: {e}')
    return _env_override(cfg)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except Exception:
        pass


def redact(text):
    """日志脱敏：遮蔽任何形如密钥的长串。"""
    if text is None:
        return text
    s = str(text)
    try:
        cfg = load_config()
        for path in _SECRET_PATHS:
            node = cfg
            for p in path:
                node = node.get(p, {}) if isinstance(node, dict) else {}
            if isinstance(node, str) and len(node) >= 8:
                s = s.replace(node, '***REDACTED***')
    except Exception:
        pass
    return s


def capability_report(cfg):
    """对外能力报告：只说明是否已配置，绝不返回密钥本体。"""
    def has_key(d, key='api_key'):
        return bool(str(d.get(key, '') or '').strip())

    primary = cfg['llm']['primary']
    fallback = cfg['llm']['fallback']
    primary_ready = has_key(primary) and bool(primary.get('model') or primary.get('endpoint_id'))
    fallback_ready = has_key(fallback) and bool(fallback.get('model'))
    vis = cfg['vision']
    vision_ready = bool(vis.get('enabled')) and has_key(vis) and bool(vis.get('model'))
    asr = cfg['asr']
    asr_ready = bool(asr.get('enabled')) and has_key(asr) and bool(asr.get('base_url'))
    tts = cfg['tts']
    tts_ready = bool(tts.get('enabled')) and has_key(tts) and bool(tts.get('base_url'))
    ims = cfg['image_search']
    image_search_ready = bool(ims.get('enabled')) and has_key(ims) and bool(ims.get('base_url'))
    demo = bool(cfg['modes']['demo'])

    if primary_ready or fallback_ready:
        llm_state = 'configured'
        llm_label = '真实 AI 已配置'
    elif demo:
        llm_state = 'demo'
        llm_label = cfg['modes']['demo_label']
    else:
        llm_state = 'unconfigured'
        llm_label = '未配置模型（请教师在教师端填写 API 配置）'

    return {
        'llm': {
            'state': llm_state,
            'label': llm_label,
            'primary': {'provider': primary.get('provider'), 'model': primary.get('model') or primary.get('endpoint_id') or '', 'configured': primary_ready},
            'fallback': {'provider': fallback.get('provider'), 'model': fallback.get('model') or '', 'configured': fallback_ready},
            'demo_mode': demo
        },
        'vision': {'state': 'configured' if vision_ready else 'unconfigured',
                   'label': '图片分析已配置' if vision_ready else '图片分析未配置（需多模态模型，DeepSeek 文本模型不支持看图）',
                   'provider': vis.get('provider'), 'model': vis.get('model') or ''},
        'image_search': {
            'state': 'configured' if image_search_ready else 'unconfigured',
            'label': '联网图片搜索已配置（专用密钥）' if image_search_ready else '联网图片搜索未配置（本地图库仍可用；需独立搜索密钥 DOUBAO_SEARCH_API_KEY）',
            'provider': ims.get('provider'),
            'base_url': ims.get('base_url'),
            # 升级对话模型不等于开通搜索；只按是否配置独立密钥报告状态。
        },
        'asr': {'state': 'configured' if asr_ready else 'unconfigured',
                'label': '语音识别已配置' if asr_ready else '语音识别（ASR）未配置——语音对话链路不完整，可先用文字输入',
                'provider': asr.get('provider') or '', 'model': asr.get('model') or ''},
        'tts': {'state': 'configured' if tts_ready else 'unconfigured',
                'label': '统一男声音色已配置' if tts_ready else '统一男声音色暂不可用，请检查语音服务配置',
                'provider': tts.get('provider') or '', 'voice': tts.get('voice') or '',
                'profile': public_profile()},
        'browser_speech_fallback': {
            'asr': '浏览器原生语音识别仅部分浏览器支持（Chrome/Edge 桌面与部分安卓），需 HTTPS 与用户首次授权；微信内置浏览器通常不支持，不作为通用方案。',
            'tts': '已关闭系统音色降级，所有终端仅使用森林小博士统一男声。'
        }
    }
