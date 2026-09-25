"""API route registration."""

from app.routes.auth import auth_bp
from app.routes.admin import admin_bp
from app.routes.comms import comms_bp
from app.routes.execution import execution_bp
from app.routes.health import health_bp
from app.routes.profiles import profiles_bp
from app.routes.projects import projects_bp
from app.routes.payments import payments_bp
from app.routes.skills import skills_bp
from app.routes.users import users_bp


def register_routes(app):
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(profiles_bp, url_prefix="/api")
    app.register_blueprint(projects_bp, url_prefix="/api")
    app.register_blueprint(execution_bp, url_prefix="/api")
    app.register_blueprint(payments_bp, url_prefix="/api")
    app.register_blueprint(comms_bp, url_prefix="/api")
    app.register_blueprint(skills_bp, url_prefix="/api/skills")
