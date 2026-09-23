import logging
import os
from logging.handlers import RotatingFileHandler


class DBHandler(logging.Handler):
    """把 WARNING 及以上日志写进 app_logs 表。防递归。"""
    _in_emit = False

    def emit(self, record):
        if DBHandler._in_emit:
            return
        if record.levelno < logging.WARNING:
            return
        DBHandler._in_emit = True
        try:
            self._write(record)
        except Exception:
            pass
        finally:
            DBHandler._in_emit = False

    def _write(self, record):
        import time
        from repositories.sqlite_repo import get_conn
        level = record.levelname
        elapsed = getattr(record, 'elapsed_ms', None)
        url     = getattr(record, 'url', None)
        method  = getattr(record, 'method', None)
        ip      = getattr(record, 'ip', None)
        uid     = getattr(record, 'uid', None)
        tb = None
        if record.exc_info:
            try:
                import traceback
                tb = ''.join(traceback.format_exception(*record.exc_info))[:4000]
            except Exception:
                pass
        conn = get_conn()
        try:
            conn.execute(
                'INSERT INTO app_logs (level, logger, message, traceback, '
                'elapsed_ms, url, method, ip, uid, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (level, record.name,
                 (record.getMessage() or '')[:1000],
                 tb, elapsed, url, method, ip, uid,
                 time.strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
        finally:
            conn.close()


_db_handler = None


def _attach_db_handler(logger):
    global _db_handler
    if _db_handler is None:
        try:
            _db_handler = DBHandler()
            _db_handler.setLevel(logging.WARNING)
        except Exception:
            return
    if _db_handler not in logger.handlers:
        logger.addHandler(_db_handler)


def setup_logger(name='tsx', log_dir='logs', level=logging.INFO):
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        _attach_db_handler(logger)
        return logger
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8',
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    _attach_db_handler(logger)
    return logger


logger = setup_logger()
