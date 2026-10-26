# -*- coding: utf-8 -*-
"""图片检索：本地动物照片图库 + 云端图片搜索（豆包/火山 Custom 文搜图）。

硬约束
------
- 本地图库条目必须带作者、来源页、许可、哈希等元数据，缺一不可收录。
- 云端搜索使用**独立的搜索专用密钥**（默认读 DOUBAO_SEARCH_API_KEY），
  绝不复用对话/视觉密钥；未配置时明确返回 unconfigured，不伪造联网结果。
- 云端失败（无权限/超时/网络错误/结构异常）时，明确返回实际状态并回退本地图库，
  前端必须如实显示“本地图库”还是“联网搜索”，不得把本地图冒充联网结果。
- 图片生成结果与真实照片是不同类别，必须显式标记，禁止把生成图当作实拍照片。

云端接口（以官方最新文档为准，续做时核对）：
  POST https://open.feedcoopapi.com/search_api/web_search
  Authorization: Bearer <专用搜索密钥>
  {"Query": "...", "SearchType": "image", "Count": 6}
  结果：Result.ImageResults[]，每项 Image.Url / Title / SiteName / Url
"""
import hashlib
import json
import os
import re
import urllib.error
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANIMALS_DIR = os.path.join(PROJECT_ROOT, 'assets', 'animals')
CATALOG_PATH = os.path.join(ANIMALS_DIR, 'catalog.json')

# 通用停用词：检索时剔除，避免“的/图片/照片”这类词影响匹配。
STOP_WORDS = {
    '的', '了', '和', '吗', '呢', '啊', '呀', '是', '在', '有', '什么', '怎么', '怎样',
    '一下', '看看', '给我', '帮我', '请', '想', '要', '图片', '照片', '图', '动物',
    '一个', '一张', '这个', '那个', '它们', '他们', '我们', '可以', '能', '吗', '？', '?',
    '。', '，', ' ', '怎么', '为什么', '如何', '样子', '长什么样',
}

# 主题词 → 用于在孩子只问“保护色/拟态/隐身”时，召回整组本地图库。
THEME_KEYWORDS = {
    '保护色': ['保护色'],
    '拟态': ['拟态'],
    '隐藏': ['隐藏', '隐身'],
    '隐身': ['隐藏', '隐身'],
    '伪装': ['伪装', '保护色', '拟态'],
}

# 口语别名 → 图库关键词（包含常见错别字/俗称）。
ALIASES = {
    '竹节虫': ['竹节虫'], '竹节': ['竹节虫'], '树枝虫': ['竹节虫'], '䗛': ['竹节虫', '叶䗛'],
    '枯叶蝶': ['枯叶蝶'], '枯叶蛱蝶': ['枯叶蝶'], '枯叶子': ['枯叶蝶'],
    '叶䗛': ['叶䗛'], '叶子虫': ['叶䗛'], '叶修': ['叶䗛'], '叶虫': ['叶䗛'],
    '树蛙': ['树蛙'], '青蛙': ['树蛙', '青蛙'], '绿青蛙': ['树蛙'], '雨蛙': ['树蛙'],
    '猫头鹰': ['猫头鹰'], '猫王鹰': ['猫头鹰'],
    '雪兔': ['雪兔'], '白兔子': ['雪兔'], '白兔': ['雪兔'], '冬兔': ['雪兔'],
    '变色龙': ['变色龙'], '避役': ['变色龙'],
    '枯叶螳螂': ['枯叶螳螂'], '兰花螳螂': ['兰花螳螂'],
    '比目鱼': ['比目鱼'], '鱼': ['鱼'],
    '北极': ['雪兔', '北极熊'], '北极熊': ['北极熊'],
    '老虎': ['老虎'], '斑马': ['斑马'], '豹子': ['花豹'], '花豹': ['花豹'], '猎豹': ['猎豹'],
    '章鱼': ['章鱼'], '八爪鱼': ['章鱼'], '乌贼': ['乌贼'], '墨鱼': ['乌贼'],
    '北极狐': ['北极狐'], '白狐': ['北极狐'], '狐狸': ['北极狐'],
    '壁虎': ['壁虎'], '叶尾壁虎': ['叶尾壁虎'], '守宫': ['壁虎'],
    '蚱蜢': ['蚱蜢'], '蚂蚱': ['蚱蜢'], '蝗虫': ['蚱蜢'], '草蜢': ['蚱蜢'],
    '螳螂': ['螳螂'], '长颈鹿': ['长颈鹿'], '大象': ['大象'], '狮子': ['狮子'],
    '火烈鸟': ['火烈鸟'], '鹦鹉': ['鹦鹉'], '彩虹鹦鹉': ['彩虹鹦鹉'],
    '孔雀': ['孔雀'], '金丝猴': ['金丝猴'], '猴子': ['猴子'],
}


class SearchError(Exception):
    """云端搜索失败；status 取值 unconfigured / unauthorized / network_error / error。"""

    def __init__(self, status, message, http_status=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.http_status = http_status


def _tokens(text):
    text = (text or '').strip().lower()
    if not text:
        return []
    for word in STOP_WORDS:
        text = text.replace(word, ' ')
    return [t for t in re.split(r'[\s,，。、；;:：?!！?]+', text) if t]


class LocalAnimalLibrary:
    """读取 assets/animals/catalog.json，按关键词检索本地实拍照片。"""

    def __init__(self, catalog_path=CATALOG_PATH):
        self.catalog_path = catalog_path
        self._mtime = None
        self._entries = []

    def _load(self):
        try:
            mtime = os.path.getmtime(self.catalog_path)
        except OSError:
            self._mtime, self._entries = None, []
            return self._entries
        if self._mtime == mtime and self._entries:
            return self._entries
        try:
            with open(self.catalog_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            self._mtime, self._entries = mtime, []
            return self._entries
        entries = []
        for item in data.get('animals', []):
            # 只收录文件真实存在、且元数据齐全的条目。
            rel = item.get('file')
            if not rel:
                continue
            full = os.path.join(ANIMALS_DIR, rel)
            if not os.path.isfile(full):
                continue
            credit = item.get('credit') or {}
            if not credit.get('license') or not credit.get('source_url'):
                continue
            entries.append(item)
        self._mtime, self._entries = mtime, entries
        return self._entries

    def available(self):
        return len(self._load()) > 0

    def count(self):
        return len(self._load())

    def all_entries(self):
        return self._load()

    def _entry_score(self, entry, tokens):
        keywords = [k.lower() for k in entry.get('keywords', [])]
        species = (entry.get('species_zh', '') + ' ' + entry.get('species_latin', '')).lower()
        score = 0
        for tok in tokens:
            if tok in species:
                score += 5
            for kw in keywords:
                if tok == kw:
                    score += 6
                elif tok and tok in kw:
                    score += 2
                elif kw and kw in tok:
                    score += 1
        return score

    def search(self, query, limit=120):
        entries = self._load()
        if not entries:
            return []
        query = (query or '').strip()
        # 空查询或纯主题词：展示全部（按主题分组排序），方便老师浏览。
        if not query:
            return [self._to_item(e) for e in entries[:limit]]
        # An explicit animal name must not fall back to unrelated theme matches.
        named=[a for a in ALIASES if a in query and a not in ('北极','鱼','䗛','竹节','枯叶子')]
        named=[a for a in named if not any(a!=b and a in b for b in named)]
        if named:
            required={k for a in named for k in ALIASES[a]}
            entries=[e for e in entries if required.intersection(e.get('keywords',[]))]
        expanded = set()
        for alias, kws in ALIASES.items():
            if alias in query:
                expanded.update(kws)
        for theme, kws in THEME_KEYWORDS.items():
            if theme in query:
                expanded.update(kws)
        tokens = _tokens(query) + list(expanded)
        if not tokens:
            return [self._to_item(e) for e in entries[:limit]]
        scored = []
        for e in entries:
            s = self._entry_score(e, tokens)
            if s > 0:
                scored.append((s, e))
        # 物种命中优先，其次按目录顺序；同分时保持稳定。
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._to_item(e) for _, e in scored[:limit]]

    def _to_item(self, entry):
        credit = entry.get('credit') or {}
        license_label = credit.get('license') or ''
        author = _clean_html(credit.get('author') or '作者待核对')
        return {
            'origin': 'local',
            'kind': '真实照片 · 本地图库',
            'id': entry.get('id'),
            'title': entry.get('title') or entry.get('species_zh'),
            'alt': entry.get('alt') or entry.get('title') or entry.get('species_zh'),
            'species_zh': entry.get('species_zh', ''),
            'species_latin': entry.get('species_latin', ''),
            'url': '/assets/animals/' + entry['file'],
            'prompt': entry.get('prompt') or '仔细看看：它的颜色和形状有什么特点？',
            'explanation': entry.get('explanation') or '请和老师一起确认动物种类，再比较它与周围环境的颜色和形状。',
            'credit': '%s · %s' % (author, license_label),
            'author': author,
            'license': license_label,
            'source_url': credit.get('source_url', ''),
            'license_url': credit.get('license_url', ''),
            'downloaded_at': credit.get('downloaded_at', ''),
            'sha256': credit.get('sha256', ''),
        }


def _clean_html(value):
    if not value:
        return ''
    text = re.sub(r'<[^>]+>', '', str(value))
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\s+', ' ', text).strip()


class DoubaoImageSearch:
    """豆包/火山 Custom 文搜图客户端；只做只读检索，不记录或转发其他密钥。"""

    def __init__(self, cfg):
        s = cfg.get('image_search') or {}
        self.base_url = (s.get('base_url') or 'https://open.feedcoopapi.com').rstrip('/')
        self.api_key = str(s.get('api_key') or '').strip()
        self.count = int(s.get('count') or 6)
        self.timeout = int(s.get('timeout_seconds') or 10)
        self.enabled = bool(s.get('enabled')) and bool(self.api_key)

    def is_ready(self):
        return self.enabled

    @staticmethod
    def _parse_error_body(body):
        """从错误响应体里提取上游错误码/消息（兼容 JSON 与纯文本）。"""
        try:
            obj = json.loads(body)
            err = ((obj.get('ResponseMetadata') or {}).get('Error') or {})
            return str(err.get('Code') or err.get('CodeN') or ''), _clean_html(err.get('Message') or '')
        except Exception:
            return '', _clean_html(body or '')[:160]

    @staticmethod
    def _is_auth_code(code, msg):
        text = ('%s %s' % (code, msg or '')).lower()
        if code in ('invalid_api_key', 'unauthorized', 'forbidden', '401', '403'):
            return True
        return any(k in text for k in ('invalid_api_key', 'invalid api key', 'unauthorized',
                                       'forbidden', 'access denied', '鉴权', '无权', '密钥无效'))

    @staticmethod
    def _is_rate_code(code, msg):
        text = ('%s %s' % (code, msg or '')).lower()
        return code in ('429', 'rate_limited', 'throttling') or 'rate limit' in text or 'quota' in text or '限流' in text

    def search(self, query, count=None):
        if not self.api_key:
            raise SearchError('unconfigured', '未配置图片搜索专用密钥 DOUBAO_SEARCH_API_KEY')
        query = (query or '').strip()
        if not query:
            return []
        # 给儿童科普检索加上下文，提升“动物 + 保护色/拟态”相关度。
        full_query = query if re.search(r'保护色|拟态|伪装|隐身|隐藏|camouflage|mimic', query) else query + ' 动物'
        payload = json.dumps({
            'Query': full_query,
            'SearchType': 'image',
            'Count': int(count or self.count),
        }, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            self.base_url + '/search_api/web_search',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + self.api_key,
                'Accept': 'application/json',
            },
            method='POST')
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            obj = json.loads(resp.read().decode('utf-8', 'ignore'))
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', 'ignore')[:400]
            except Exception:
                pass
            # 部分网关把错误体放在 JSON 里（HTTP 状态码仍是 401/403）。
            err_code, err_msg = self._parse_error_body(body)
            if e.code in (401, 403) or self._is_auth_code(err_code, err_msg):
                raise SearchError('unauthorized',
                                  '图片搜索密钥无效或无权限（HTTP %s%s）。请确认已开通联网搜索 Custom 文搜图服务，并在后端配置专用搜索密钥（不是对话模型密钥）。'
                                  % (e.code, ('：' + err_code) if err_code else ''), http_status=e.code)
            if e.code == 429 or self._is_rate_code(err_code, err_msg):
                raise SearchError('rate_limited', '图片搜索服务暂时繁忙（HTTP 429），稍后再试。', http_status=429)
            raise SearchError('error', '图片搜索返回错误 HTTP %s：%s' % (e.code, body), http_status=e.code)
        except urllib.error.URLError as e:
            raise SearchError('network_error', '图片搜索网络请求失败：%s' % getattr(e, 'reason', e))
        except SearchError:
            raise
        except Exception as e:
            raise SearchError('error', '图片搜索响应解析失败：%s' % e)

        # 实测该接口即使密钥无效也返回 HTTP 200，错误信息放在 ResponseMetadata.Error，
        # Result 为 null；必须先识别错误，再按缺失 ImageResults 兜底。
        err = ((obj.get('ResponseMetadata') or {}).get('Error') or {}) if isinstance(obj, dict) else {}
        if err:
            err_code = str(err.get('Code') or err.get('CodeN') or '')
            err_msg = _clean_html(err.get('Message') or '')
            if self._is_auth_code(err_code, err_msg):
                raise SearchError(
                    'unauthorized',
                    '图片搜索专用密钥无效或未授权（%s%s）。请在火山引擎开通“联网搜索 Custom（文搜图）”服务，'
                    '获取该服务的专用 API Key，并配置到后端 DOUBAO_SEARCH_API_KEY（或 config.json 的 image_search.api_key）；'
                    '该密钥与对话/视觉模型密钥不是同一个，升级对话模型不会获得搜索权限。'
                    % (err_code, ('：' + err_msg) if err_msg else ''))
            if self._is_rate_code(err_code, err_msg):
                raise SearchError('rate_limited', '图片搜索服务暂时繁忙或额度不足（%s），稍后再试。' % (err_code or err_msg))
            raise SearchError('error', '图片搜索返回错误（%s：%s）' % (err_code or 'unknown', err_msg or '无错误描述'))

        items = []
        try:
            results = obj['Result']['ImageResults'] or []
        except Exception:
            raise SearchError('error', '图片搜索响应结构异常（缺少 Result.ImageResults），请核对官方文档是否更新。')
        seen = set()
        for r in results:
            image = r.get('Image') or {}
            url = image.get('Url') or ''
            if not url.startswith('https://') or url in seen:
                continue
            seen.add(url)
            page_url = r.get('Url') or ''
            site = r.get('SiteName') or ''
            title = _clean_html(r.get('Title') or '') or query
            items.append({
                'origin': 'web',
                'kind': '联网搜索 · 真实照片（来自第三方网页，需按来源要求使用）',
                'title': title[:60],
                'alt': title,
                'url': url,
                'prompt': '仔细看看：它的颜色和形状有什么特点？和周围环境像不像？',
                'explanation': '请和老师一起核对动物种类，再比较它与周围环境的颜色、形状。',
                'credit': '来源：%s' % (site or page_url or '未知站点'),
                'source_url': page_url if page_url.startswith('https://') else '',
                'license': '',
                'author': '',
                'license_url': '',
            })
        return items[: self.count]


def media_search(cfg, query, session_id=None, prefer='cloud'):
    """统一入口：先本地图库，再按配置尝试云端；失败时回退本地并如实标注。

    返回 dict：
      items / message / local_count / web_count / cloud_state / cloud_error
    cloud_state: ready / unconfigured / unauthorized / network_error /
                 rate_limited / error / skipped
    """
    library = LocalAnimalLibrary()
    local_items = library.search(query)

    searcher = DoubaoImageSearch(cfg)
    cloud_items, cloud_state, cloud_error = [], 'skipped', ''

    # 空查询只浏览本地图库；本地关键词命中足够时也默认优先本地（儿童场景需物种准确）。
    if query.strip() and prefer != 'local':
        try:
            if searcher.is_ready():
                cloud_items = searcher.search(query)
                cloud_state = 'ready'
            else:
                cloud_state = 'unconfigured'
                cloud_error = '尚未配置图片搜索专用密钥（DOUBAO_SEARCH_API_KEY），当前只显示本地图库。'
        except SearchError as e:
            cloud_state, cloud_error = e.status, e.message
            cloud_items = []

    # 本地图库永远排在前面（物种经过核对、许可可追溯），联网结果作为补充。
    items = local_items + cloud_items
    messages = []
    if local_items:
        messages.append('本地图库 %d 张（已核对物种与许可）' % len(local_items))
    if cloud_state == 'ready':
        if cloud_items:
            messages.append('联网搜索补充 %d 张（来源已标注，使用前请查看来源要求）' % len(cloud_items))
        else:
            messages.append('联网搜索没有找到可用图片，已显示本地图库。')
    elif cloud_state == 'unconfigured':
        messages.append('联网图片搜索未开通，当前为本地图库。')
    elif cloud_state in ('unauthorized', 'network_error', 'rate_limited', 'error'):
        messages.append('联网搜索暂时不可用（%s），已回退本地图库。' % cloud_state)
    if not items:
        messages.append('本地图库暂时没有这种动物的照片，请换一个关键词（如竹节虫、枯叶蝶、树蛙、猫头鹰、雪兔）。')
    return {
        'ok': True,
        'items': items,
        'message': '；'.join(messages),
        'local_count': len(local_items),
        'web_count': len(cloud_items),
        'cloud_state': cloud_state,
        'cloud_error': cloud_error,
        'local_library_count': library.count(),
    }


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()
