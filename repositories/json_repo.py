# repositories/json_repo.py
import json
import os
import threading
from repositories.base import BaseRepository


class JsonRepository(BaseRepository):
    """基于 JSON 文件的通用数据访问实现

    用法：
        repo = JsonRepository('data/menu.json')
        items = repo.get_all()
        repo.create({'name': '牛肉泡馍', 'price': 24})
    """

    # 文件锁，防止并发写入
    _locks = {}
    _lock_guard = threading.Lock()

    def __init__(self, filepath, id_field='id', auto_id=True):
        self.filepath = filepath
        self.id_field = id_field
        self.auto_id = auto_id

        # 先注册锁（必须在 _write 之前）
        with self._lock_guard:
            if filepath not in self._locks:
                self._locks[filepath] = threading.Lock()

        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # 确保文件存在
        if not os.path.exists(filepath):
            self._write([])

    def _lock(self):
        return self._locks[self.filepath]

    def _read(self):
        """读文件"""
        with self._lock():
            if not os.path.exists(self.filepath):
                return []
            with open(self.filepath, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []

    def _write(self, data):
        """写文件（先写临时文件再替换，防止写一半崩溃）"""
        with self._lock():
            tmp = self.filepath + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.filepath)

    def _next_id(self, items):
        """生成下一个 ID"""
        if not items:
            return 1
        ids = [it.get(self.id_field, 0) for it in items]
        numeric = [i for i in ids if isinstance(i, int)]
        return max(numeric) + 1 if numeric else 1

    # ---------- 接口实现 ----------
    def get_all(self):
        return self._read()

    def find_by_id(self, id):
        for item in self._read():
            if item.get(self.id_field) == id:
                return item
        return None

    def find(self, **conditions):
        """按条件查询（多个条件 AND）"""
        results = []
        for item in self._read():
            if all(item.get(k) == v for k, v in conditions.items()):
                results.append(item)
        return results

    def create(self, data):
        items = self._read()
        if self.auto_id and self.id_field not in data:
            data[self.id_field] = self._next_id(items)
        items.append(data)
        self._write(items)
        return data

    def update(self, id, data):
        items = self._read()
        for i, item in enumerate(items):
            if item.get(self.id_field) == id:
                item.update(data)
                items[i] = item
                self._write(items)
                return item
        return None

    def delete(self, id):
        items = self._read()
        new_items = [it for it in items if it.get(self.id_field) != id]
        if len(new_items) == len(items):
            return False
        self._write(new_items)
        return True

    def count(self):
        return len(self._read())