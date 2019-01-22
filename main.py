from app import app, db
from models import Language, Word, Definition, WordClassifier, SoundChangeSet
import views
import util

db.create_tables([
    Language, Word, Definition, WordClassifier, SoundChangeSet
])

app.run()
