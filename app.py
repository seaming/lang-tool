import os

from flask import Flask
from peewee import SqliteDatabase

APP_ROOT = os.path.dirname(os.path.realpath(__file__))
DATABASE = os.path.join(APP_ROOT, 'data.db')
SECRET_KEY = os.urandom(24)
DEBUG = True

app = Flask(__name__)
app.config.from_object(__name__)

db = SqliteDatabase(app.config['DATABASE'], pragmas={'foreign_keys': 1})
