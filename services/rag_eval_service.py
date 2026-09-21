# services/rag_eval_service.py
"""RAG 评估：记录每次检索，统计命中率"""
import time
from collections import Counter
from datetime import datetime
from repositories.json_repo import JsonRepository
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, 'data', 'rag_logs.json')
_repo = JsonRepository(LOG_PATH)

# 判定"未命中"的标志词
MISS_KEYWORDS = ['抱歉', '没有这方面', '无法回答', '不清楚', '没有找到']


class RagEvalService:
    """RAG 评估"""

    def log(self, question, answer, hit_count=0, elapsed_ms=0, is_hit=None, uid=None):
        """记录一次 RAG 查询"""
        if is_hit is None:
            is_hit = not any(kw in (answer or '') for kw in MISS_KEYWORDS)

        record = {
            'question': (question or '')[:100],
            'answer': (answer or '')[:100],
            'hit_count': hit_count,
            'elapsed_ms': round(elapsed_ms, 1),
            'is_hit': is_hit,
            'uid': uid,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        _repo.create(record)
        return record

    def get_stats(self):
        """统计报告"""
        logs = _repo.get_all()
        total = len(logs)
        if total == 0:
            return {
                'total': 0,
                'hit_count': 0,
                'miss_count': 0,
                'hit_rate': 0,
                'avg_elapsed_ms': 0,
                'today': {'total': 0, 'hit': 0, 'miss': 0},
                'miss_questions': [],
            }

        hit_count = sum(1 for x in logs if x.get('is_hit'))
        miss_count = total - hit_count
        hit_rate = round(hit_count / total * 100, 1)

        elapsed_list = [x.get('elapsed_ms', 0) for x in logs if x.get('elapsed_ms')]
        avg_elapsed = round(sum(elapsed_list) / len(elapsed_list), 1) if elapsed_list else 0

        today = datetime.now().strftime('%Y-%m-%d')
        today_logs = [x for x in logs if x.get('date') == today]

        # 未命中问题 Top 10
        miss_questions = Counter(
            x['question'] for x in logs if not x.get('is_hit') and x.get('question')
        ).most_common(10)

        return {
            'total': total,
            'hit_count': hit_count,
            'miss_count': miss_count,
            'hit_rate': hit_rate,
            'avg_elapsed_ms': avg_elapsed,
            'today': {
                'total': len(today_logs),
                'hit': sum(1 for x in today_logs if x.get('is_hit')),
                'miss': sum(1 for x in today_logs if not x.get('is_hit')),
            },
            'miss_questions': [{'q': q, 'count': c} for q, c in miss_questions],
        }


rag_eval_service = RagEvalService()