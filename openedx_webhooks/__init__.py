import logging
import os
import sys
import traceback

from celery import Celery
from flask import Flask
from flask_sslify import SSLify
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.flask import FlaskIntegration
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import import_string

__version__ = "0.1.0"

log_level = os.environ.get('LOGLEVEL', 'INFO').upper()
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(log_level)
logger.addHandler(handler)
logger.setLevel(log_level)

# Github3 is chatty on info-level, quiet it.
logging.getLogger("github3").setLevel("WARN")

celery = Celery(strict_typing=False)


def expand_config(name=None):
    if not name:
        name = "default"
    return "openedx_webhooks.config.{classname}Config".format(
        classname=name.capitalize(),
    )


def create_app(config=None):
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app)   # type: ignore[method-assign]
    config = config or os.environ.get("OPENEDX_WEBHOOKS_CONFIG") or "default"
    # Instantiate the config object because we rely on the __init__
    # function to translate config between heroku and what sqlalchemy wants
    config_obj = import_string(expand_config(config))()
    app.config.from_object(config_obj)

    create_celery_app(app)
    if not app.debug:
        SSLify(app)

    # attach our blueprints
    from .github_views import github_bp
    app.register_blueprint(github_bp, url_prefix="/github")
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
    celery.conf.update(app.config)
    class ContextTask(celery.Task): # type: ignore[name-defined]
        abstract = True
        def __call__(self, *args, **kwargs):
            if "wsgi_environ" in kwargs:
                wsgi_environ = kwargs.pop("wsgi_environ")
            else:
                wsgi_environ = None
            try:
                with app.app_context():
                    if wsgi_environ:
                        with app.request_context(wsgi_environ):
                            return self.run(*args, **kwargs)
                    else:
                        return self.run(*args, **kwargs)
            except Exception:
                # By default, celery will store an exception if it occurs,
                # but we don't want the exception object, we want a traceback.
                return traceback.format_exc()

    celery.Task = ContextTask
    return celery
