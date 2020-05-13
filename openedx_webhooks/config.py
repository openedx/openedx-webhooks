import os


class DefaultConfig(object):
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "secrettoeveryone")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///openedx_webhooks.db")
    GITHUB_OAUTH_CLIENT_ID = os.environ.get("GITHUB_OAUTH_CLIENT_ID")
    GITHUB_OAUTH_CLIENT_SECRET = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET")
    GITHUB_WEBHOOKS_SECRET = os.environ.get("GITHUB_WEBHOOKS_SECRET")
    JIRA_OAUTH_CONSUMER_KEY = os.environ.get("JIRA_OAUTH_CONSUMER_KEY")
    JIRA_OAUTH_RSA_KEY = os.environ.get("JIRA_OAUTH_RSA_KEY")
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_EAGER_PROPAGATES_EXCEPTIONS = True
    CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://")
    CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://")


class WorkerConfig(DefaultConfig):
    CELERY_IMPORTS = (
        'openedx_webhooks.tasks.github',
        'openedx_webhooks.tasks.jira',
        'openedx_webhooks.tasks.example',
    )


class DevelopmentConfig(DefaultConfig):
    DEBUG = True


class TestingConfig(DefaultConfig):
    TESTING = True
