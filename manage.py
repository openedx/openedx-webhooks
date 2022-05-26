#!/usr/bin/env python
import click


from flask_sqlalchemy import SQLAlchemy
from openedx_webhooks import create_app, db


app = create_app()

@click.group()
def cli():
    pass

@click.command()
def dbcreate():
    "Creates database tables from SQLAlchemy models"
    with app.app_context():
        db.create_all()
        db.session.commit()


@click.command()
def dbdrop():
    "Drops database tables"
    if click.confirm("Are you sure you want to lose all your data"):
        with app.app_context():
            db.drop_all()
            db.session.commit()


cli.add_command(dbcreate)
cli.add_command(dbdrop)


if __name__ == "__main__":
    cli()
