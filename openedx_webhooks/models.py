# coding=utf-8
from __future__ import unicode_literals
from flask.ext.sqlalchemy import SQLAlchemy
from flask_dance.consumer.backend.sqla import OAuthConsumerMixin

db = SQLAlchemy()

class OAuth(db.Model, OAuthConsumerMixin):
    pass
