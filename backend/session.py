# -*- coding: utf-8 -*-
"""会话管理：隔离、长记忆（≥10 轮完整保留）、上下文预算与摘要、持久化。

关键保证（对应需求）：
1. **至少 10 轮完整问答进入模型上下文**：构建上下文时强制保留最近 `min_keep_turns`(默认 10) 轮
   用户+助手消息原文，即使超出 token 预算也不裁剪（改为显式告警）。
2. **跨文字/语音/照片共享上下文**：三种输入写入同一条消息流。
3. **服务端会话隔离**：每个会话独立文件 + 独立锁；学生端与教师端命名空间分离，互相不可读写。
4. **刷新恢复 + 清空**：会话按 TTL 持久化到磁盘，刷新后凭 session_id 恢复；提供新建/清空接口。
5. **图片不无上限保留**：只保留图片的**文字分析结果**与引用标签，原图不落盘；图片引用最多保留 `max_image_refs` 条。
"""
import json
import os
import threading
import time
import uuid

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sessions')

STUDENT_PREFIX = 's_'
TEACHER_PREFIX = 't_'


def _now():
    return time.time()


def est_tokens(text):
    """粗略 token 估算：中文约 1 字 ≈ 0.7 token，英文约 4 字符 ≈ 1 token。取偏保守估计。"""
    if not text:
        return 0
    s = str(text)
    cjk = sum(1 for ch in s if '\u4e00' <= ch <= '\u9fff')
    other = len(s) - cjk
    return int(cjk * 0.75 + other / 3.0) + 1


class Session:
    def __init__(self, sid, mode='student'):
        self.id = sid
        self.mode = mode  # student | teacher
        self.stage_id = None
        self.created_at = _now()
        self.updated_at = _now()
        self.messages = []          # [{role, content, ts, kind, turn}]
        self.summary = ''           # 早期内容的摘要（超长时生成）
        self.image_refs = []        # [{label, ts, description}] 仅文字，无原图
        self.lock = threading.RLock()

    # ---------- 写入 ----------
    def add(self, role, content, kind='text', image_ref=None):
        with self.lock:
            turn = (self.messages[-1]['turn'] + 1) if (self.messages and self.messages[-1]['role'] == 'assistant') else \
                   (self.messages[-1]['turn'] if self.messages else 1)
            if role == 'user' and (not self.messages or self.messages[-1]['role'] == 'assistant'):
                turn = (self.messages[-1]['turn'] + 1) if self.messages else 1
            self.messages.append({'role': role, 'content': content, 'ts': _now(),
                                  'kind': kind, 'turn': turn})
            self.updated_at = _now()
            if image_ref:
                self.image_refs.append(image_ref)

    def turns(self):
        """返回完整轮数（user+assistant 成对计数）。"""
        users = sum(1 for m in self.messages if m['role'] == 'user')
        assts = sum(1 for m in self.messages if m['role'] == 'assistant')
        return min(users, assts)

    # ---------- 上下文构建 ----------
    def build_context(self, max_history_turns=40, min_keep_turns=10, token_budget=6000, summarizer=None):
        """返回 (history_msgs, meta)。history_msgs 为 [{role, content}]，不含本轮新问题。"""
        with self.lock:
            msgs = list(self.messages)

        # 按“轮”切分：一轮 = 该 turn 的所有消息
        by_turn = {}
        for m in msgs:
            by_turn.setdefault(m['turn'], []).append(m)
        turns_sorted = sorted(by_turn.keys())
        total_turns = len(turns_sorted)

        keep_turns = turns_sorted[-max_history_turns:] if total_turns > max_history_turns else turns_sorted
        dropped = [t for t in turns_sorted if t not in keep_turns]

        def flatten(turn_list):
            out = []
            for t in turn_list:
                for m in by_turn[t]:
                    if m['role'] in ('user', 'assistant') and m.get('content'):
                        out.append({'role': m['role'], 'content': m['content']})
            return out

        history = flatten(keep_turns)
        est = est_tokens(self.summary) + sum(est_tokens(h['content']) for h in history)
        warning = None

        # 超预算：优先裁剪到 min_keep_turns，但绝不低于 min_keep_turns
        if est > token_budget and len(keep_turns) > min_keep_turns:
            keep_turns = keep_turns[-min_keep_turns:]
            dropped = [t for t in turns_sorted if t not in keep_turns]
            history = flatten(keep_turns)
            est = est_tokens(self.summary) + sum(est_tokens(h['content']) for h in history)
            warning = (f'上下文超出预算，已保留最近 {min_keep_turns} 轮完整对话并压缩更早内容。')

        if est > token_budget:
            # 已到 min_keep_turns 仍超预算 → 显式提示（不静默截断最近 10 轮）
            warning = (f'注意：即使只保留最近 {min_keep_turns} 轮完整对话，估算 token({est}) 仍超出预算({token_budget})。'
                       f'最近 {min_keep_turns} 轮已按需求完整保留；建议缩短单条消息长度或提高 context_token_budget。')

        # 丢弃的更早轮次 → 摘要
        if dropped and summarizer:
            old_text = '\n'.join(f"{m['role']}:{m['content']}" for t in dropped for m in by_turn[t]
                                 if m.get('content'))
            new_summary = summarizer(old_text)
            if new_summary:
                self.summary = (self.summary + ' ' + new_summary).strip()[:1200]

        if self.summary:
            history = [{'role': 'system', 'content': '【更早对话摘要】' + self.summary}] + history

        meta = {
            'kept_turns': len(keep_turns),
            'total_turns': total_turns,
            'dropped_turns': len(dropped),
            'min_keep_turns': min_keep_turns,
            'est_tokens': est,
            'token_budget': token_budget,
            'has_summary': bool(self.summary),
            'warning': warning,
            'image_refs_kept': len(self.image_refs),
        }
        return history, meta

    def prune_image_refs(self, max_image_refs=5):
        with self.lock:
            if len(self.image_refs) > max_image_refs:
                self.image_refs = self.image_refs[-max_image_refs:]

    # ---------- 序列化 ----------
    def to_dict(self, include_messages=True):
        d = {
            'id': self.id, 'mode': self.mode, 'stage_id': self.stage_id,
            'created_at': self.created_at, 'updated_at': self.updated_at,
            'summary': self.summary, 'turns': self.turns(),
            'image_refs': self.image_refs,
        }
        if include_messages:
            d['messages'] = self.messages
        return d

    @classmethod
    def from_dict(cls, d):
        s = cls(d['id'], d.get('mode', 'student'))
        s.stage_id = d.get('stage_id')
        s.created_at = d.get('created_at', _now())
        s.updated_at = d.get('updated_at', _now())
        s.messages = d.get('messages', [])
        s.summary = d.get('summary', '')
        s.image_refs = d.get('image_refs', [])
        return s


class SessionStore:
    def __init__(self, ttl_hours=12):
        self.ttl = ttl_hours * 3600
        self._cache = {}
        self._lock = threading.RLock()
        os.makedirs(DATA_DIR, exist_ok=True)

    def _path(self, sid):
        safe = ''.join(ch for ch in sid if ch.isalnum() or ch in '_-')
        return os.path.join(DATA_DIR, safe + '.json')

    def create(self, mode='student'):
        prefix = TEACHER_PREFIX if mode == 'teacher' else STUDENT_PREFIX
        sid = prefix + uuid.uuid4().hex[:20]
        s = Session(sid, mode)
        with self._lock:
            self._cache[sid] = s
        self.persist(s)
        return s

    def get(self, sid, mode=None):
        if not sid:
            return None
        if mode == 'student' and sid.startswith(TEACHER_PREFIX):
            return None  # 权限隔离：学生端不得访问教师会话
        if mode == 'teacher' and sid.startswith(STUDENT_PREFIX):
            return None
        with self._lock:
            s = self._cache.get(sid)
        if s is None:
            p = self._path(sid)
            if os.path.isfile(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        d = json.load(f)
                    if _now() - d.get('updated_at', 0) > self.ttl:
                        return None  # 超过明确期限，不再恢复
                    s = Session.from_dict(d)
                    with self._lock:
                        self._cache[sid] = s
                except Exception:
                    return None
        return s

    def persist(self, session):
        try:
            tmp = self._path(session.id) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, ensure_ascii=False)
            os.replace(tmp, self._path(session.id))
        except Exception:
            pass

    def clear(self, session):
        with session.lock:
            session.messages = []
            session.summary = ''
            session.image_refs = []
            session.updated_at = _now()
        self.persist(session)
        return session

    def delete(self, sid):
        with self._lock:
            self._cache.pop(sid, None)
        p = self._path(sid)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass


class RateLimiter:
    """简单滑动窗口限流：按会话 + 全局。"""

    def __init__(self):
        self._hits = {}
        self._lock = threading.RLock()

    def allow(self, key, limit_per_minute):
        now = _now()
        with self._lock:
            arr = [t for t in self._hits.get(key, []) if now - t < 60]
            if len(arr) >= limit_per_minute:
                self._hits[key] = arr
                return False, len(arr)
            arr.append(now)
            self._hits[key] = arr
            return True, len(arr)

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)
