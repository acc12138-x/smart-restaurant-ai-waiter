from flask import jsonify


def success(data=None, msg='ok'):
    return jsonify({
        'code': 0,
        'msg': msg,
        'data': data,
    })


def error(code=400, msg='请求错误'):
    return jsonify({
        'code': code,
        'msg': msg,
        'data': None,
    }), code
