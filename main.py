from app import app, db, util, views
from app.models import Language, Word, Definition, WordClassifier, SoundChangeSet

db.create_tables([
    Language, Word, Definition, WordClassifier, SoundChangeSet
])

app.run()
