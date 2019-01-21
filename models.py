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
    parent = ForeignKeyField('self', null=True, backref='daughters')

    use_classes = BooleanField(default=True)

    def parts_of_speech(self):
        return self.classifiers.where(WordClassifier.type == CLASSIFIER_TYPE_POS)

    def classes(self):
        return self.classifiers.where(WordClassifier.type == CLASSIFIER_TYPE_CLASS)

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

    parent = ForeignKeyField('self', null=True, backref='descendants')


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
