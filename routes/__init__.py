from routes.page_routes import page_bp
from routes.api_routes import api_bp
from routes.auth_routes import auth_bp
from routes.points_routes import points_bp
from routes.track_routes import track_bp
from routes.docs_routes import docs_bp
from routes.admin_routes import admin_bp
from routes.admin_page_routes import admin_page_bp

__all__ = ['page_bp', 'api_bp', 'auth_bp', 'points_bp',
           'track_bp', 'docs_bp', 'admin_bp', 'admin_page_bp']
