from flask import request, render_template, redirect, url_for, flash, abort
from peewee import fn, JOIN

from app import app, db
from models import Language, Word, Definition, WordClassifier, CLASSIFIER_TYPE_POS, CLASSIFIER_TYPE_CLASS


def get_lang(code):
    lang = Language.get_or_none(code=code)
    if not lang:
        abort(404)
    return lang


@app.route('/')
def home():
    return render_template(
        'home.html',
        langs=Language.select().order_by(fn.Lower(Language.name))
    )


@app.route('/add_lang/', methods=['GET'])
def add_lang():
    return render_template('add_lang.html')


@app.route('/add_lang/', methods=['POST'])
def add_lang_post():
    code = request.form.get('code')
    if not code:
        flash('You must enter a code', 'danger')
        return redirect(url_for('add_lang'))

    if Language.get_or_none(code=code):
        flash('A language with this code already exists', 'danger')
        return redirect(url_for('add_lang'))

    lang = Language.create(code=code)

    name = request.form.get('name')
    if name:
        lang.name = name
        lang.save()

    return redirect(url_for('view_lang', code=lang.code))


@app.route('/lang/')
def null_lang():
    return redirect(url_for('home'))


@app.route('/lang/<code>/')
def view_lang(code):
    lang = get_lang(code)

    query = request.args.get('q', '')
    sort = {
        'nat': Word.nat,
        'en': Definition.en,
        'pos': Definition.pos,
        'class': Definition.classes,
    }.get(request.args.get('sort', 'nat'))

    words = lang.words.join(Definition).where(Definition.en.contains(
        query) | Word.nat.contains(query)).group_by(Word.nat).order_by(sort)

    return render_template('view_lang.html', lang=lang, words=words)


@app.route('/lang/<code>/settings/', methods=['GET'])
def edit_lang(code):
    lang = get_lang(code)
    return render_template(
        'edit_lang.html',
        lang=lang,
        pos=lang.parts_of_speech(),
        classes=lang.classes()
    )


@app.route('/lang/<code>/settings/', methods=['POST'])
def save_lang(code):
    lang = get_lang(code)

    lang.name = request.form.get('name', 'Unnamed language')
    lang.description = request.form.get('description', '')
    lang.use_classes = request.form.get('use_classes') is not None
    lang.abbreviate_classes = request.form.get(
        'abbreviate_classes') is not None
    lang.save()

    classifiers = {}

    i = 0
    pos_abbreviations = []
    while True:
        long = request.form.get(f'pos_long-{i}')
        abbr = request.form.get(f'pos_abbr-{i}')

        if not (long and abbr):
            break

        pos_abbreviations.append(abbr)
        classifiers[(abbr, CLASSIFIER_TYPE_POS)] = long
        i += 1

    i = 0
    class_abbreviations = []
    while True:
        long = request.form.get(f'classes_long-{i}')
        abbr = request.form.get(f'classes_abbr-{i}')

        if not (long and abbr):
            break

        class_abbreviations.append(abbr)
        classifiers[(abbr, CLASSIFIER_TYPE_CLASS)] = long
        i += 1

    WordClassifier.delete().where((WordClassifier.type == CLASSIFIER_TYPE_POS)
                                  & (WordClassifier.abbr.not_in(pos_abbreviations))).execute()
    WordClassifier.delete().where((WordClassifier.type == CLASSIFIER_TYPE_CLASS)
                                  & (WordClassifier.abbr.not_in(class_abbreviations))).execute()

    for k, v in classifiers.items():
        c, created = WordClassifier.get_or_create(
            lang=lang, type=k[1], abbr=k[0], defaults={'long': v})
        if not created:
            c.long = v
        c.save()

    return redirect(url_for('view_lang', code=code))


@app.route('/lang/<code>/add_word/', methods=['GET'])
def add_word(code):
    lang = get_lang(code)
    return render_template(
        'add_word.html',
        lang=lang,
        pos=lang.parts_of_speech(),
        classes=lang.classes()
    )


@app.route('/lang/<code>/add_word/', methods=['POST'])
def save_word(code):
    lang = get_lang(code)

    nat = request.form.get('nat')
    count = int(request.form.get('counter'))

    definitions = []
    i = 0
    while i < count:
        definition = request.form.get(f'en-{i}')
        pos = request.form.get(f'pos-{i}')

        classes = []
        for c in lang.classes():
            if request.form.get(f'class_{c.abbr}-{i}') is not None:
                classes.append(c.abbr)

        definitions.append((definition, pos, classes))
        i += 1

    if not definitions:
        flash('You must enter at least one definition', 'danger')
        return redirect(url_for('add_word', code=lang.code))

    print(definitions)

    word = Word.create(lang=lang, nat=nat)
    for i, d in enumerate(definitions):
        Definition.create(word=word, order=i,
                          en=d[0], pos=d[1], classes=','.join(d[2]))

    flash(
        f"Word added! Click <a href='{url_for('view_word', id=word.id)}'>here</a> to see it", 'success')

    return redirect(url_for('add_word', code=lang.code))


@app.route('/word/<id>/')
def view_word(id):
    word = Word.get_by_id(id)
    return render_template('view_word.html', word=word)


@app.route('/word/<id>/delete/', methods=['GET', 'POST'])
def delete_word(id):
    word = Word.get_by_id(id)

    if request.method == 'POST':
        lang = word.lang
        word.delete_instance()
        flash('Word deleted!', 'success')
        return redirect(url_for('view_lang', code=lang.code))

    return render_template('delete_word.html', word=word)
