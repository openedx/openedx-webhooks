import logging
import os
import sys

from celery import Celery
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_sslify import SSLify
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.flask import FlaskIntegration
from werkzeug.middleware.proxy_fix import ProxyFix


__version__ = "0.1.0"

rootLogger = logging.getLogger()
rootLogger.addHandler(logging.StreamHandler(sys.stderr))
rootLogger.setLevel(logging.INFO)

db = SQLAlchemy()
celery = Celery(strict_typing=False)


def expand_config(name=None):
    if not name:
        name = "default"
    return "openedx_webhooks.config.{classname}Config".format(
        classname=name.capitalize(),
    )


def create_app(config=None):
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app)
    config = config or os.environ.get("OPENEDX_WEBHOOKS_CONFIG") or "default"
    app.config.from_object(expand_config(config))

    db.init_app(app)
    create_celery_app(app)
    if not app.debug:
        SSLify(app)

    # attach Flask-Dance blueprints
    from .oauth import jira_bp as jira_oauth_bp
    app.register_blueprint(jira_oauth_bp, url_prefix="/login")
    from .oauth import github_bp as github_oauth_bp
    app.register_blueprint(github_oauth_bp, url_prefix="/login")

    # attach our blueprints
    from .github_views import github_bp
    app.register_blueprint(github_bp, url_prefix="/github")
    from .jira_views import jira_bp
    app.register_blueprint(jira_bp, url_prefix="/jira")
    from .ui import ui as ui_blueprint
    app.register_blueprint(ui_blueprint)
    from .tasks import tasks as tasks_blueprint
    app.register_blueprint(tasks_blueprint, url_prefix="/tasks")

    return app


def create_celery_app(app=None, config="worker"):
    """
    adapted from http://flask.pocoo.org/docs/0.10/patterns/celery/
    (added the wsgi_environ stuff)
    """
    if os.environ.get("SENTRY_DSN", ""):
        sentry_sdk.init(integrations=[CeleryIntegration(), FlaskIntegration()])

    app = app or create_app(config=config)
    celery.main = app.import_name
    celery.conf["BROKER_URL"] = app.config["CELERY_BROKER_URL"]
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            if "wsgi_environ" in kwargs:
                wsgi_environ = kwargs.pop("wsgi_environ")
            else:
                wsgi_environ = None
            with app.app_context():
                if wsgi_environ:
                    with app.request_context(wsgi_environ):
                        return TaskBase.__call__(self, *args, **kwargs)
                else:
                    return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    return celery
