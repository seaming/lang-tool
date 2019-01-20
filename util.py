import mistune
from flask import request, Markup
from app import app, db
from models import WordClassifier, CLASSIFIER_TYPE_POS, CLASSIFIER_TYPE_CLASS

render_markdown = mistune.Markdown()


@app.before_request
def before_request():
    db.connect()


@app.after_request
def after_request(response):
    db.close()
    return response


@app.template_filter()
def markdown(text):
    return Markup(render_markdown(text))


@app.template_filter()
def split(text, sep):
    return text.split(sep)


@app.template_filter()
def convert_pos(abbr, lang):
    c = WordClassifier.get_or_none(WordClassifier.lang == lang, WordClassifier.type ==
                               CLASSIFIER_TYPE_POS, WordClassifier.abbr == abbr)
    return c.long if c else abbr


@app.template_filter()
def convert_class(abbr, lang):
    c = WordClassifier.get_or_none(WordClassifier.lang == lang, WordClassifier.type ==
                               CLASSIFIER_TYPE_CLASS, WordClassifier.abbr == abbr)
    return c.long if c else abbr