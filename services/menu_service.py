# services/menu_service.py
import json
import os
from configs.config import get_config

_cfg = get_config()


class MenuService:
    """菜单业务逻辑"""

    def __init__(self):
        self.menu_path = os.path.join(_cfg.DATA_DIR, 'menu.json')
        self._cache = None
        self._cache_mtime = 0

    def _load(self):
        """读菜单，带文件修改时间缓存"""
        if not os.path.exists(self.menu_path):
            return []
        mtime = os.path.getmtime(self.menu_path)
        if self._cache is not None and mtime == self._cache_mtime:
            return self._cache
        with open(self.menu_path, 'r', encoding='utf-8') as f:
            self._cache = json.load(f)
            self._cache_mtime = mtime
        return self._cache

    def get_all(self):
        """获取完整菜单（按分类）"""
        return self._load()

    def get_flat(self):
        """获取扁平化的菜品列表（用于搜索）"""
        flat = []
        for cat in self._load():
            for item in cat.get('items', []):
                flat.append({
                    'name': item['name'],
                    'price': float(item.get('price', 0)),
                    'emoji': item.get('emoji', ''),
                    'category': cat['category'],
                    'desc': item.get('desc', ''),
                })
        return flat

    def find_dish(self, name):
        """按名字模糊查找菜品"""
        if not name:
            return None

        import re
        raw = name.strip()

        # 只去掉开头的量词，不动菜品名里的"小份/大份"
        cleaned = re.sub(r'^[一二三四五六七八九十百千0-9]+份', '', raw).strip()
        cleaned = re.sub(r'^[一二三四五六七八九十百千0-9]+个', '', cleaned).strip()
        if not cleaned:
            cleaned = raw

        flat = self.get_flat()

        # 1. 精确匹配
        for dish in flat:
            if dish['name'] == raw or dish['name'] == cleaned:
                return dish

        # 2. 包含匹配，优先选菜品名最长的
        matches = []
        for dish in flat:
            dn = dish['name']
            if cleaned in dn or dn in cleaned:
                matches.append((len(dn), dish))
        if matches:
            matches.sort(key=lambda x: -x[0])
            return matches[0][1]

        return None

    def get_categories(self):
        """获取所有分类名"""
        return [cat['category'] for cat in self._load()]


# 单例
menu_service = MenuService()