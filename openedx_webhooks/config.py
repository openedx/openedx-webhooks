import os


class DefaultConfig:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "secrettoeveryone")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///openedx_webhooks.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GITHUB_WEBHOOKS_SECRET = os.environ.get("GITHUB_WEBHOOKS_SECRET")
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_EAGER_PROPAGATES = True
    BROKER_URL = os.environ.get('REDIS_TLS_URL', os.environ.get("REDIS_URL", "redis://"))
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_TLS_URL', os.environ.get("REDIS_URL", "redis://"))

    def __init__(self):
        # Convert the heroku postgres URI to one that is compatible with SQLAlchemy
        # See https://help.heroku.com/ZKNTJQSK/why-is-sqlalchemy-1-4-x-not-connecting-to-heroku-postgres
        uri = self.SQLALCHEMY_DATABASE_URI
        if uri.startswith("postgres://"):
            uri = uri.replace("postgres://", "postgresql://", 1)
            self.SQLALCHEMY_DATABASE_URI = uri

        # Don't require cert validation if usng redis over TLS because heroku redis uses self signed certs.
        # https://help.heroku.com/HC0F8CUS/redis-connection-issues
        redis_tls_options = "?ssl_cert_reqs=none"
        if self.BROKER_URL.startswith("rediss"):
            self.BROKER_URL += redis_tls_options
            self.CELERY_RESULT_BACKEND += redis_tls_options


class WorkerConfig(DefaultConfig):
    CELERY_IMPORTS = (
        'openedx_webhooks.tasks.github',
        'openedx_webhooks.tasks.example',
    )


class DevelopmentConfig(DefaultConfig):
    DEBUG = True


class TestingConfig(DefaultConfig):
    TESTING = True
