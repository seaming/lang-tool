from flask import request, render_template, redirect, url_for, flash, abort
from peewee import fn, JOIN
from uuid import uuid4, UUID

from app import app, db
from models import (
    Language,
    Word,
    Definition,
    WordClassifier,
    SoundChangeSet,
    CLASSIFIER_TYPE_POS,
    CLASSIFIER_TYPE_CLASS
)


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

###############################################################################
##                                                                           ##
##                               LANGUAGE VIEWS                              ##
##                                                                           ##
###############################################################################


@app.route('/add_lang/')
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

    SoundChangeSet.create(id=uuid4(), parent_lang=lang,
                          name='Pronunciation estimation', pronunciation=True)

    name = request.form.get('name')
    if name:
        lang.name = name
        lang.save()

    return redirect(url_for('edit_lang', code=lang.code))


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
        query) | Word.nat.contains(query)).group_by(Word.id).order_by(sort)

    return render_template('view_lang.html', lang=lang, words=words)


@app.route('/lang/<code>/settings/')
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

    parent = request.form.get('parent')
    parent = Language.get_or_none(Language.code == parent)

    if parent in lang.get_potential_parents() or parent is None:
        lang.parent = parent
    else:
        flash('Could not add parent language as it would create a cycle in the family tree', 'danger')

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


@app.route('/lang/<code>/delete/', methods=['GET', 'POST'])
def delete_lang(code):
    lang = get_lang(code)

    if request.method == 'POST':
        lang.delete_instance()
        flash('Language deleted!', 'success')
        return redirect(url_for('home'))

    return render_template('delete_lang.html', lang=lang)


###############################################################################
##                                                                           ##
##                                 WORD VIEWS                                ##
##                                                                           ##
###############################################################################


def add_word(initial_word, definitions):
    # w is a dictionary with fields corresponding to the Word model's fields

    def create_rows(word, visited_langs=[]):
        # creates table rows that will be mass inserted

        word_rows = [word]
        visited_langs.append(word['lang'].code)

        for set in word['lang'].sc_sets:
            # make sure to prevent derivation loops
            if set.autoderive and set.target_lang.code not in visited_langs:
                w = create_rows({
                    **word,
                    'id': uuid4(),
                    'lang': set.target_lang,
                    'nat': set.apply(word['nat']),
                    'autoderived': True
                }, visited_langs)

                word_rows += w

        return word_rows

    word_rows = create_rows(initial_word)
    definition_rows = []

    print(definitions)
    print(word_rows)

    for w in word_rows:
        for i, d in enumerate(definitions):
            definition_rows.append({
                'id': uuid4(),
                'word': w['id'],
                'order': i,
                'en': d['def'],
                'pos': d['pos'],
                'classes': d['class']
            })

    print('\n\n'.join(str(x) for x in definition_rows))

    with db.atomic():
        Word.insert_many(word_rows).execute()
        Definition.insert_many(definition_rows).execute()


@app.route('/lang/<code>/add_word/')
def add_word_get(code):
    lang = get_lang(code)
    return render_template(
        'add_word.html',
        lang=lang,
        pos=lang.parts_of_speech(),
        classes=lang.classes()
    )


@app.route('/lang/<code>/add_word/', methods=['POST'])
def add_word_post(code):
    lang = get_lang(code)

    nat = request.form.get('nat')
    notes = request.form.get('notes', '')
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

        definitions.append({
            'def': definition,
            'pos': pos,
            'class': '\n'.join(classes)
        })

        i += 1

    if not definitions:
        flash('You must enter at least one definition', 'danger')
        return redirect(url_for('add_word_get', code=lang.code))

    word_id = uuid4()
    add_word({'id': word_id, 'lang': lang,
              'nat': nat, 'notes': notes}, definitions)


    word = Word.get_by_id(word_id)

    flash(
        f"Word added! Click <a href='{url_for('view_word', id=word.id.hex)}'>here</a> to see it", 'success')

    return redirect(url_for('add_word_get', code=lang.code))


@app.route('/word/<id>/')
def view_word(id):
    word = Word.get_by_id(UUID(id))
    return render_template('view_word.html', word=word)


@app.route('/word/<id>/edit/')
def edit_word(id):
    word = Word.get_by_id(UUID(id))
    return render_template('edit_word.html', word=word)


@app.route('/word/<id>/edit/', methods=['POST'])
def save_word(id):
    word = Word.get_by_id(UUID(id))

    word.nat = request.form.get('nat')
    word.notes = request.form.get('notes', '')
    word.save()

    count = int(request.form.get('counter'))

    definitions = []
    i = 0
    while i < count:
        definition = request.form.get(f'en-{i}')
        pos = request.form.get(f'pos-{i}')
        def_id = request.form.get(f'id_{i}')

        classes = []
        for c in word.lang.classes():
            if request.form.get(f'class_{c.abbr}-{i}') is not None:
                classes.append(c.abbr)

        definitions.append({
            'id': def_id,
            'def': definition,
            'pos': pos,
            'class': '\n'.join(classes)
        })

        i += 1

    if not definitions:
        flash('Words must have at least one definition', 'danger')
        return redirect(url_for('view_word', id=id))

    for i, d in enumerate(definitions):
        if d['id']:
            definition = Definition.get_by_id(d['id'])

            if not d['def']:
                definition.delete_instance()
                continue

            definition.en = d['def']
            definition.order = i
            definition.pos = d['pos']
            definition.classes = d['class']
            definition.save()

        elif d['def']:
            Definition.create(
                id=uuid4(),
                word=word,
                order=i,
                en=d['def'],
                pos=d['pos'],
                classes=d['class']
            )

    flash(
        f"Word updated!", 'success')

    return redirect(url_for('view_word', id=id))


@app.route('/word/<id>/delete/', methods=['GET', 'POST'])
def delete_word(id):
    word = Word.get_by_id(UUID(id))

    if request.method == 'POST':
        lang = word.lang
        word.delete_instance()
        flash('Word deleted!', 'success')
        return redirect(url_for('view_lang', code=lang.code))

    return render_template('delete_word.html', word=word)


###############################################################################
##                                                                           ##
##                           SOUND CHANGE SET VIEWS                          ##
##                                                                           ##
###############################################################################

@app.route('/lang/<code>/add_set/')
def add_set(code):
    lang = get_lang(code)
    set = SoundChangeSet.create(id=uuid4(), parent_lang=lang)
    return redirect(url_for('edit_set', id=set.id.hex))


@app.route('/set/<id>')
def view_set(id):
    set = SoundChangeSet.get_by_id(UUID(id))
    return render_template('view_set.html', set=set)


@app.route('/set/<id>/edit')
def edit_set(id):
    set = SoundChangeSet.get_by_id(UUID(id))
    return render_template(
        'edit_set.html',
        set=set,
        valid_targets=Language.select().where(Language.code != set.parent_lang.code)
    )


@app.route('/set/<id>/edit', methods=['POST'])
def save_set(id):
    set = SoundChangeSet.get_by_id(UUID(id))
    set.changes = request.form.get('changes', '')

    if not set.pronunciation:
        set.name = request.form.get('name', 'Unnamed set')
        set.description = request.form.get('description', '')
        set.autoderive = request.form.get('autoderive') is not None

        target = request.form.get('target')
        target = Language.get_or_none(Language.code == target)

        if target != set.parent_lang or target is None:
            set.target_lang = target

    set.save()

    return render_template('view_set.html', set=set)


@app.route('/set/<id>/delete', methods=['GET', 'POST'])
def delete_set(id):
    set = SoundChangeSet.get_by_id(UUID(id))

    if request.method == 'POST':
        lang = set.parent_lang
        set.delete_instance()
        flash('Set deleted!', 'success')
        return redirect(url_for('view_lang', code=lang.code))

    return render_template('delete_set.html', set=set)
