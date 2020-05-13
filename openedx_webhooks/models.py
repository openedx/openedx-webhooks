from flask_dance.consumer.backend.sqla import OAuthConsumerMixin

from openedx_webhooks import db


class OAuth(db.Model, OAuthConsumerMixin):
    pass
