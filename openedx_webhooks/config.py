# coding=utf-8
from __future__ import unicode_literals
import os


class DefaultConfig(object):
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "secrettoeveryone")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///openedx_webhooks.db")
    GITHUB_OAUTH_CLIENT_ID = os.environ.get("GITHUB_OAUTH_CLIENT_ID")
    GITHUB_OAUTH_CLIENT_SECRET = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET")
    JIRA_OAUTH_CONSUMER_KEY = os.environ.get("JIRA_OAUTH_CONSUMER_KEY")
    JIRA_OAUTH_RSA_KEY = os.environ.get("JIRA_OAUTH_RSA_KEY")
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_EAGER_PROPAGATES_EXCEPTIONS = True
    # CELERY_BROKER_URL = os.environ.get("RABBITMQ_BIGWIG_TX_URL", "amqp://")
    CELERY_BROKER_URL = "ironmq://"  # project ID and token are automatically read from env vars
    # TODO: Why do we need to use Redis for results?
    CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://")
    SENTRY_PROCESSORS = ["openedx_webhooks.raven_processors.RequestsURLProcessor"]


class WorkerConfig(DefaultConfig):
    # CELERY_BROKER_URL = os.environ.get("RABBITMQ_BIGWIG_RX_URL", "amqp://")
    pass


class DevelopmentConfig(DefaultConfig):
    DEBUG = True


class TestingConfig(DefaultConfig):
    TESTING = True
