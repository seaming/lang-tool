from flask import request, render_template, redirect, url_for, flash, abort
from peewee import fn, JOIN, DoesNotExist
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

    WordClassifier.delete().where((WordClassifier.lang == lang)
                                  & (WordClassifier.type == CLASSIFIER_TYPE_POS)
                                  & (WordClassifier.abbr.not_in(pos_abbreviations))).execute()

    WordClassifier.delete().where((WordClassifier.lang == lang)
                                  & (WordClassifier.type == CLASSIFIER_TYPE_CLASS)
                                  & (WordClassifier.abbr.not_in(class_abbreviations))).execute()

    for k, v in classifiers.items():
        c, created = WordClassifier.get_or_create(
            lang=lang, type=k[1], abbr=k[0], defaults={'long': v})
        if not created:
            c.long = v
        c.save()

    flash('Successfully updated language settings!', 'success')

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

        for sc_set in word['lang'].sc_sets:
            # make sure to prevent derivation loops
            if sc_set.autoderive and sc_set.target_lang.code not in visited_langs:
                w = create_rows({
                    **word,
                    'id': uuid4(),
                    'lang': sc_set.target_lang,
                    'nat': sc_set.apply(word['nat'])[0],
                    'parent': word['id'],
                    'autoderived': True
                }, visited_langs)

                word_rows += w

        return word_rows

    word_rows = create_rows(initial_word)
    definition_rows = []

    for w in word_rows:
        for i, d in enumerate(definitions):
            definition_rows.append({
                'id': uuid4(),
                'word': w['id'],
                'order': i,
                'en': d['def'],
                'pos': d['pos'],
                'classes': d['class'],
                'notes': d['notes']
            })

    with db.atomic():
        Word.insert_many(word_rows).execute()
        Definition.insert_many(definition_rows).execute()

    for w in word_rows:
        if 'parent' in w:
            word = Word.get_by_id(w['id'])
            word.parent = Word.get_by_id(w['parent'])
            word.save()


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
    count = int(request.form.get('counter'))
    word_notes = request.form.get('word_notes') or ''

    definitions = []
    i = 0
    while i < count:
        definition = request.form.get(f'en-{i}')
        if not definition.strip():
            i += 1
            continue

        notes = request.form.get(f'def_notes-{i}') or ''
        pos = request.form.get(f'pos-{i}')

        classes = []
        for c in lang.classes():
            if request.form.get(f'class_{c.abbr}-{i}') is not None:
                classes.append(c.abbr)

        definitions.append({
            'def': definition,
            'pos': pos,
            'class': '\n'.join(classes),
            'notes': notes
        })

        i += 1

    if not definitions:
        flash('You must enter at least one definition', 'danger')
        return redirect(url_for('add_word_get', code=lang.code))

    word_id = uuid4()
    add_word({'id': word_id, 'lang': lang, 'nat': nat, 'notes': word_notes}, definitions)

    word = Word.get_by_id(word_id)

    flash(
        f"Word added! Click <a href='{url_for('view_word', id=word.id.hex)}'>here</a> to see it", 'success')

    return redirect(url_for('add_word_get', code=lang.code))


@app.route('/word/<id>/')
def view_word(id):
    word = Word.get_by_id(UUID(id))
    return render_template('view_word.html', word=word)


@app.route('/derive_word/<id>/<set_id>')
def derive_word(id, set_id):
    word = Word.get_by_id(UUID(id))
    sc_set = SoundChangeSet.get_by_id(UUID(set_id))

    definitions = [{'def': d.en, 'pos': d.pos, 'class': d.classes, 'notes': d.notes} for d in word.definitions]

    word_id = uuid4()
    add_word({'id': word_id, 'lang': sc_set.target_lang, 'parent': word,
              'nat': sc_set.apply(word.nat)[0]}, definitions)

    word = Word.get_by_id(word_id)

    flash(f"Word added!", 'success')

    return redirect(url_for('edit_word', id=word.id))


@app.route('/word/<id>/edit/')
def edit_word(id):
    word = Word.get_by_id(UUID(id))
    return render_template('edit_word.html', word=word)


def update_descendants(word):
    for d_word in word.descendants:
        if d_word.autoderived:
            try:
                sc_set = word.lang.sc_sets.where(
                    SoundChangeSet.target_lang == d_word.lang
                ).get()

            except DoesNotExist:
                continue

            d_word.nat = sc_set.apply(word.nat)[0]
            d_word.save()

            update_descendants(d_word)


@app.route('/word/<id>/edit/', methods=['POST'])
def save_word(id):
    word = Word.get_by_id(UUID(id))

    word.nat = request.form.get('nat')
    word.notes = request.form.get('word_notes') or ''
    
    if request.form.get('remove_autoderived'):
        word.autoderived = False
    
    word.save()

    update_descendants(word)

    count = int(request.form.get('counter'))

    definitions = []
    i = 0
    while i < count:
        definition = request.form.get(f'en-{i}')
        notes = request.form.get(f'def_notes-{i}') or ''
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
            'class': '\n'.join(classes),
            'notes': notes
        })

        i += 1

    if not definitions:
        flash('Words must have at least one definition', 'danger')
        return redirect(url_for('edit_word', id=id))

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
            definition.notes = d['notes']
            definition.save()

        elif d['def']:
            Definition.create(
                id=uuid4(),
                word=word,
                order=i,
                en=d['def'],
                pos=d['pos'],
                classes=d['class'],
                notes=d['notes']
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


@app.route('/apply_ruleset', methods=['GET'])
def apply_ruleset():
    sc_set = SoundChangeSet.get_by_id(request.args.get('set_id'))
    words = request.args.get('words')
    return '\n'.join(sc_set.apply(words))


@app.route('/lang/<code>/add_set/')
def add_set(code):
    lang = get_lang(code)
    sc_set = SoundChangeSet.create(id=uuid4(), parent_lang=lang)
    return redirect(url_for('edit_set', id=sc_set.id.hex))


@app.route('/set/<id>')
def view_set(id):
    sc_set = SoundChangeSet.get_by_id(UUID(id))
    return render_template('view_set.html', set=sc_set)


@app.route('/set/<id>/edit')
def edit_set(id):
    sc_set = SoundChangeSet.get_by_id(UUID(id))
    return render_template(
        'edit_set.html',
        set=sc_set,
        valid_targets=Language.select().where(Language.code != sc_set.parent_lang.code)
    )


@app.route('/set/<id>/edit', methods=['POST'])
def save_set(id):
    sc_set = SoundChangeSet.get_by_id(UUID(id))
    sc_set.changes = request.form.get('changes', '')

    if not sc_set.pronunciation:
        sc_set.name = request.form.get('name', 'Unnamed set')
        sc_set.description = request.form.get('description', '')
        sc_set.autoderive = request.form.get('autoderive') is not None

        target = request.form.get('target')
        target = Language.get_or_none(Language.code == target)

        if target != sc_set.parent_lang or target is None:
            sc_set.target_lang = target

    sc_set.save()

    return render_template('view_set.html', set=sc_set)


@app.route('/set/<id>/delete', methods=['GET', 'POST'])
def delete_set(id):
    sc_set = SoundChangeSet.get_by_id(UUID(id))

    if request.method == 'POST':
        lang = sc_set.parent_lang
        sc_set.delete_instance()
        flash('Set deleted!', 'success')
        return redirect(url_for('view_lang', code=lang.code))

    return render_template('delete_set.html', set=sc_set)
