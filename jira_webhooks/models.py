from __future__ import unicode_literals
from flask.ext.sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class OAuthCredential(db.Model):
    __tablename__ = "oauth_credentials"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256))
    token = db.Column(db.String(256), nullable=False)
    secret = db.Column(db.String(256), nullable=False)
    created_on = db.Column(db.DateTime, nullable=False)
