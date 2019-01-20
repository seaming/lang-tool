from Conlanger.sce import apply_ruleset
from peewee import *

from app import db


class BaseModel(Model):
    class Meta:
        database = db


class Language(BaseModel):
    code = CharField(primary_key=True)

    name = CharField(default='Unnamed language')
    description = TextField(default='')

    use_classes = BooleanField(default=True)

    def parts_of_speech(self):
        return self.classifiers.where(WordClassifier.type == CLASSIFIER_TYPE_POS)

    def classes(self):
        return self.classifiers.where(WordClassifier.type == CLASSIFIER_TYPE_CLASS)


class Word(BaseModel):
    lang = ForeignKeyField(Language, backref='words')
    nat = CharField()


class Definition(BaseModel):
    word = ForeignKeyField(Word, backref='definitions', on_delete='CASCADE')
    order = SmallIntegerField()

    en = CharField()
    pos = CharField()
    classes = CharField()


CLASSIFIER_TYPE_POS = 1
CLASSIFIER_TYPE_CLASS = 2


class WordClassifier(BaseModel):
    # combines parts of speech and classes

    lang = ForeignKeyField(Language, backref='classifiers')
    type = SmallIntegerField()

    abbr = CharField()
    long = CharField()

    class Meta:
        primary_key = CompositeKey('lang', 'type', 'abbr')
