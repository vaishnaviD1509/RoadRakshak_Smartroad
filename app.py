import os
from flask import Flask, request, flash, redirect, url_for
from config import Config, BASE_DIR
from models import db


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)

    db.init_app(app)

    from routes.main_routes import main_bp
    app.register_blueprint(main_bp)

    from routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp)

    from routes.citizen_routes import citizen_bp
    app.register_blueprint(citizen_bp)

    from routes.tracking_routes import tracking_bp
    app.register_blueprint(tracking_bp)

    from routes.admin_routes import admin_bp
    app.register_blueprint(admin_bp)

    from routes.map_routes import map_bp
    app.register_blueprint(map_bp)

    from routes.csrf import register_csrf
    register_csrf(app)

    @app.errorhandler(413)
    def file_too_large(e):
        flash("That file is too large. Please upload an image smaller than 5 MB.", "danger")
        return redirect(request.referrer or url_for("main.index")), 302

    # Registered here in later stages:
    # from routes.api_routes import api_bp

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)