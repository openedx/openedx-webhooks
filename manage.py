#!/usr/bin/env python
from flask.ext.script import Manager
from jira_webhooks import app
from jira_webhooks.models import db

manager = Manager(app)


@manager.command
def dbcreate():
    "Creates database tables from SQLAlchemy models"
    db.create_all()
    db.session.commit()


if __name__ == "__main__":
    manager.run()
