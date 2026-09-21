# repositories/base.py
from abc import ABC, abstractmethod


class BaseRepository(ABC):
    """数据访问层抽象基类

    所有数据源（JSON / MySQL / Redis）都实现这套接口，
    上层业务代码只依赖接口，不关心底层实现。
    """

    @abstractmethod
    def get_all(self):
        """获取所有记录"""
        pass

    @abstractmethod
    def find_by_id(self, id):
        """按 ID 查询"""
        pass

    @abstractmethod
    def create(self, data):
        """创建一条记录"""
        pass

    @abstractmethod
    def update(self, id, data):
        """更新一条记录"""
        pass

    @abstractmethod
    def delete(self, id):
        """删除一条记录"""
        pass