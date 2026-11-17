import os


class DefaultConfig:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "secrettoeveryone")
    GITHUB_WEBHOOKS_SECRET = os.environ.get("GITHUB_WEBHOOKS_SECRET")
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_EAGER_PROPAGATES = True
    BROKER_URL = os.environ.get('REDIS_TLS_URL', os.environ.get("REDIS_URL", "redis://"))
    # With the Redis broker, a task whose countdown is longer than the
    # visibility timeout (one hour by default) is redelivered and run again.
    # A rate-limit retry can wait up to an hour plus jitter, so give it room.
    # https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html#visibility-timeout
    BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 2 * 60 * 60}
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_TLS_URL', os.environ.get("REDIS_URL", "redis://"))

    def __init__(self):
        # Don't require cert validation if usng redis over TLS because heroku redis uses self signed certs.
        # https://help.heroku.com/HC0F8CUS/redis-connection-issues
        redis_tls_options = "?ssl_cert_reqs=none"
        if self.BROKER_URL.startswith("rediss"):
            self.BROKER_URL += redis_tls_options
            self.CELERY_RESULT_BACKEND += redis_tls_options


class WorkerConfig(DefaultConfig):
    CELERY_IMPORTS = (
        'openedx_webhooks.tasks.github',
    )


class DevelopmentConfig(DefaultConfig):
    DEBUG = True


class TestingConfig(DefaultConfig):
    TESTING = True
