# coding=utf-8
from __future__ import print_function, unicode_literals

# UTF-8 stderr: http://stackoverflow.com/a/2001767/141395
import codecs
import sys
reload(sys)
sys.setdefaultencoding('utf-8')
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
sys.stderr = codecs.getwriter('utf-8')(sys.stderr)

import os

from flask import Flask
from flask_sslify import SSLify
from .oauth import jira_bp, github_bp
from .models import db
from bugsnag.flask import handle_exceptions

app = Flask(__name__)
handle_exceptions(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
config_env_vars = (
    "JIRA_OAUTH_CONSUMER_KEY", "JIRA_OAUTH_RSA_KEY",
    "GITHUB_OAUTH_CLIENT_ID", "GITHUB_OAUTH_CLIENT_SECRET",
)
for env_var in config_env_vars:
    app.config[env_var] = os.environ.get(env_var)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secrettoeveryone")
app.register_blueprint(jira_bp, url_prefix="/login")
app.register_blueprint(github_bp, url_prefix="/login")
db.init_app(app)
if not app.debug:
    sslify = SSLify(app)

from .views import *


if __name__ == "__main__":
    app.run()
