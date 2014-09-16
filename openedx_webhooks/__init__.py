from __future__ import print_function, unicode_literals

import os

from flask import Flask
from .oauth import jira_bp, github_bp
from .models import db
from bugsnag.flask import handle_exceptions

app = Flask(__name__)
handle_exceptions(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secrettoeveryone")
app.register_blueprint(jira_bp, url_prefix="/login")
app.register_blueprint(github_bp, url_prefix="/login")
db.init_app(app)

from .views import *

if __name__ == "__main__":
    app.run()
