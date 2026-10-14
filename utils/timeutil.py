# utils/timeutil.py
"""统一的时间来源 —— 业务时间一律按北京时间（UTC+8）。

背景：容器默认跑在 UTC。如果直接用 time.strftime() / datetime.now()，订单时间会
比实际早 8 小时；更严重的是凌晨 00:00–08:00 的单子会被记成前一天（本店营业到
次日 02:00，这类单子不少），于是"今日营业额""时段分布""时段热力图"全都错位。

这里用固定的 +08:00 偏移，而不是 ZoneInfo('Asia/Shanghai')：
中国没有夏令时，固定偏移永远正确，而且不依赖镜像里装没装 tzdata。
"""
import os
import time
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8), 'CST')


def enforce_process_tz():
    """把当前进程的时区强制设为北京时间。

    容器默认跑在 UTC，而全项目的时间戳都来自 time.strftime() / datetime.now()，
    也就是"进程本地时间"。所以只要在这里把时区定死，订单时间、日志时间、
    统计口径会**一起**变正确，不必去改二十处调用点。

    用 POSIX 时区串 'CST-8'（POSIX 里偏移方向与直觉相反，-8 表示 UTC+8）而不是
    'Asia/Shanghai'：glibc 能直接解析，不依赖镜像里有没有 tzdata；中国没有夏令时，
    固定偏移永远正确。Windows 没有 time.tzset()，跳过即可（开发机本身就是本地时间）。
    """
    os.environ['TZ'] = 'CST-8'
    if hasattr(time, 'tzset'):
        time.tzset()


def now():
    """当前北京时间（带时区的 datetime）"""
    return datetime.now(CST)


def now_str():
    """'2026-10-14 20:15:30' —— 与库里 created_at 的格式一致"""
    return now().strftime('%Y-%m-%d %H:%M:%S')


def today_str():
    """'2026-10-14'"""
    return now().strftime('%Y-%m-%d')


def date_str(dt=None):
    """把 datetime 格式化成日期串；不传则取今天"""
    return (dt or now()).strftime('%Y-%m-%d')


def parse(ts):
    """把库里存的 'YYYY-MM-DD HH:MM:SS' 解析成带时区的北京时间；失败返回 None"""
    if not ts:
        return None
    try:
        return datetime.strptime(str(ts)[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=CST)
    except Exception:
        return None
