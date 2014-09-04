#!/usr/bin/env python
from flask.ext.script import Manager
from openedx_webhooks import app
from openedx_webhooks.models import db

manager = Manager(app)


@manager.command
def dbcreate():
    "Creates database tables from SQLAlchemy models"
    db.create_all()
    db.session.commit()


if __name__ == "__main__":
    manager.run()
