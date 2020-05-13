from flask_dance.consumer.storage.sqla import OAuthConsumerMixin

from openedx_webhooks import db


class OAuth(db.Model, OAuthConsumerMixin):
    pass
