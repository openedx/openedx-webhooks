# coding=utf-8
from __future__ import unicode_literals

from openedx_webhooks import db
from flask_dance.consumer.backend.sqla import OAuthConsumerMixin


class OAuth(db.Model, OAuthConsumerMixin):
    pass
