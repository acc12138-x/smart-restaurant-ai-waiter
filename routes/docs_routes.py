# routes/docs_routes.py
from flask import Blueprint, jsonify, Response
from services.openapi_service import get_openapi_spec

docs_bp = Blueprint('docs', __name__)


@docs_bp.route('/api/openapi.json')
def openapi_json():
    """OpenAPI 规范"""
    return jsonify(get_openapi_spec())


@docs_bp.route('/api/docs')
def swagger_ui():
    """Swagger UI 页面"""
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>API 文档 · 同盛祥</title>
<link rel="stylesheet" href="https://cdn.bootcdn.net/ajax/libs/swagger-ui/5.10.5/swagger-ui.min.css">
<style>
  body{margin:0;background:#FAF7F2;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;}
  .topbar{display:none;}
  .swagger-ui .info .title{color:#1A0E05;}
  .swagger-ui .opblock.opblock-get{border-color:#C8412A;background:rgba(200,65,42,.05);}
  .swagger-ui .opblock.opblock-post{border-color:#8B3A1E;background:rgba(139,58,30,.05);}
  .swagger-ui .opblock.opblock-get .opblock-summary-method{background:#C8412A;}
  .swagger-ui .opblock.opblock-post .opblock-summary-method{background:#8B3A1E;}
  .swagger-ui .btn.authorize{color:#C8412A;border-color:#C8412A;}
  .swagger-ui .btn.authorize svg{fill:#C8412A;}
  .back-bar{position:fixed;top:16px;right:16px;z-index:9999;}
  .back-bar a{background:#C8412A;color:#fff;text-decoration:none;padding:8px 18px;border-radius:100px;font-size:13px;font-weight:700;}
</style>
</head>
<body>
<div class="back-bar"><a href="/">← 返回首页</a></div>
<div id="swagger-ui"></div>
<script src="https://cdn.bootcdn.net/ajax/libs/swagger-ui/5.10.5/swagger-ui-bundle.min.js"></script>
<script>
window.onload = () => {
  window.ui = SwaggerUIBundle({
    url: '/api/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [SwaggerUIBundle.presets.apis],
    layout: 'BaseLayout',
  });
};
</script>
</body>
</html>'''
    return Response(html, mimetype='text/html')