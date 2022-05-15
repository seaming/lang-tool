import mistune
from flask import request, Markup
from app import app, db
from models import WordClassifier, CLASSIFIER_TYPE_POS, CLASSIFIER_TYPE_CLASS

render_markdown = mistune.create_markdown(plugins=['table', 'strikethrough'])


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
def char_count(text, n):
    sentences = list(reversed(text.split('. ')))
    result = sentences.pop()
    while len('. '.join(result)) <= n and sentences:
        result += '. ' + sentences.pop()
    if not result.endswith('.'):
        result += '...' if sentences else '.'
    return result


@app.template_filter()
def pluralize(n, singular='', plural='s'):
    if n == 1:
        return singular
    return plural


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