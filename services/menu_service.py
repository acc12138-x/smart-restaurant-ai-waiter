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
                    'stock': item.get('stock', None),
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

    def _save(self, data):
        """写回菜单文件并清缓存"""
        with open(self.menu_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._cache = None
        self._cache_mtime = 0

    def add_item(self, category, item):
        """新增菜品"""
        data = self._load()
        for cat in data:
            if cat['category'] == category:
                if any(it['name'] == item['name'] for it in cat['items']):
                    raise ValueError(f'菜品「{item["name"]}」已存在')
                cat['items'].append(item)
                self._save(data)
                return item
        raise ValueError(f'分类「{category}」不存在')

    def update_item(self, category, old_name, new_item):
        """修改菜品（按旧名定位）"""
        data = self._load()
        for cat in data:
            if cat['category'] == category:
                for i, it in enumerate(cat['items']):
                    if it['name'] == old_name:
                        # 改名时检查新名冲突
                        if new_item['name'] != old_name:
                            if any(x['name'] == new_item['name'] for x in cat['items']):
                                raise ValueError(f'菜品「{new_item["name"]}」已存在')
                        cat['items'][i] = new_item
                        self._save(data)
                        return new_item
                raise ValueError(f'菜品「{old_name}」不存在')
        raise ValueError(f'分类「{category}」不存在')

    def delete_item(self, category, name):
        """删除菜品"""
        data = self._load()
        for cat in data:
            if cat['category'] == category:
                before = len(cat['items'])
                cat['items'] = [it for it in cat['items'] if it['name'] != name]
                if len(cat['items']) == before:
                    raise ValueError(f'菜品「{name}」不存在')
                self._save(data)
                return True
        raise ValueError(f'分类「{category}」不存在')

    def add_category(self, name):
        """新增分类"""
        data = self._load()
        if any(cat['category'] == name for cat in data):
            raise ValueError(f'分类「{name}」已存在')
        new_cat = {'category': name, 'items': []}
        data.append(new_cat)
        self._save(data)
        return new_cat

    def delete_category(self, name):
        """删除分类（必须为空）"""
        data = self._load()
        for i, cat in enumerate(data):
            if cat['category'] == name:
                if cat['items']:
                    raise ValueError(f'分类「{name}」下还有 {len(cat["items"])} 道菜，先清空')
                del data[i]
                self._save(data)
                return True
        raise ValueError(f'分类「{name}」不存在')

    # ---------- v3.8 库存 ----------

    def get_stock(self, name):
        """查某菜库存，返回 int 或 None（无限）"""
        dish = self.find_dish(name)
        if not dish:
            return 0
        return dish.get('stock', None)

    def is_sold_out(self, name):
        """库存是否为 0"""
        stk = self.get_stock(name)
        return stk is not None and stk <= 0

    def deduct_stock(self, name, qty):
        """扣库存。返回 (成功, 剩余库存或 None)"""
        data = self._load()
        for cat in data:
            for it in cat.get('items', []):
                if it['name'] == name:
                    cur = it.get('stock', None)
                    if cur is None:
                        return (True, None)
                    if cur < qty:
                        return (False, cur)
                    it['stock'] = cur - qty
                    self._save(data)
                    return (True, it['stock'])
        return (False, 0)

    def restore_stock(self, name, qty):
        """恢复库存（取消订单时调用）。无限库存的菜跳过。"""
        data = self._load()
        for cat in data:
            for it in cat.get('items', []):
                if it['name'] == name:
                    cur = it.get('stock', None)
                    if cur is None:
                        return
                    it['stock'] = cur + qty
                    self._save(data)
                    return

    def set_stock(self, name, stock):
        """后台设置库存：stock 传 None 或 '' 表示无限"""
        data = self._load()
        for cat in data:
            for it in cat.get('items', []):
                if it['name'] == name:
                    if stock is None or stock == '':
                        it.pop('stock', None)
                    else:
                        it['stock'] = int(stock)
                    self._save(data)
                    return it

    def get_categories(self):
        """获取所有分类名"""
        return [cat['category'] for cat in self._load()]


# 单例
menu_service = MenuService()