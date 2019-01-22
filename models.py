from Conlanger.sce import apply_ruleset
from peewee import *
from uuid import uuid4

from app import db


class BaseModel(Model):
    class Meta:
        database = db


class Language(BaseModel):
    code = CharField(primary_key=True)

    name = CharField(default='Unnamed language')
    description = TextField(default='')
    parent = ForeignKeyField('self', backref='daughters',
                             null=True, on_delete='SET NULL')

    use_classes = BooleanField(default=True)

    def parts_of_speech(self):
        return self.classifiers.where(WordClassifier.type == CLASSIFIER_TYPE_POS)

    def classes(self):
        return self.classifiers.where(WordClassifier.type == CLASSIFIER_TYPE_CLASS)

    def pronounce(self, word):
        # applies pronunciation estimation ruleset to word
        set = SoundChangeSet.get_or_none(
            SoundChangeSet.parent_lang == self, SoundChangeSet.pronunciation == True)
        if set:
            return set.apply(word)
        # we should always be able to find a set, but if we cant fall back to just the word
        return word

    def get_potential_parents(self):
        daughters = set()

        def get_daughters(l):
            if l.code in daughters:
                return
            daughters.add(l.code)
            for d in l.daughters:
                get_daughters(d)

        get_daughters(self)
        langs = Language.select().where(Language.code.not_in(daughters))
        return langs


class Word(BaseModel):
    id = UUIDField(primary_key=True)

    lang = ForeignKeyField(Language, backref='words', on_delete='CASCADE')
    nat = CharField()
    notes = TextField(default='')

    autoderived = BooleanField(default=False)

    parent = ForeignKeyField(
        'self', backref='descendants', null=True, on_delete='SET NULL')


class Definition(BaseModel):
    id = UUIDField(primary_key=True)

    word = ForeignKeyField(Word, backref='definitions', on_delete='CASCADE')
    order = SmallIntegerField()

    en = CharField()
    pos = CharField()
    classes = CharField()


CLASSIFIER_TYPE_POS = 1
CLASSIFIER_TYPE_CLASS = 2


class WordClassifier(BaseModel):
    # combines parts of speech and classes

    lang = ForeignKeyField(
        Language, backref='classifiers', on_delete='CASCADE')
    type = SmallIntegerField()

    abbr = CharField()
    long = CharField()

    class Meta:
        primary_key = CompositeKey('lang', 'type', 'abbr')


class SoundChangeSet(BaseModel):
    id = UUIDField(primary_key=True)

    name = CharField(default='Unnamed set')
    description = TextField(default='')

    autoderive = BooleanField(default=False)
    pronunciation = BooleanField(default=False)

    changes = TextField(default='')

    parent_lang = ForeignKeyField(
        Language, backref='sc_sets', on_delete='CASCADE')
    target_lang = ForeignKeyField(
        Language, backref='arriving_sc_sets', null=True, on_delete='SET NULL')

    def count_rules(self):
        return len([l for l in self.changes.splitlines() if (l.strip() and not l.strip().startswith('//'))])

    def apply(self, word):
        return apply_ruleset([word], self.changes)[0]