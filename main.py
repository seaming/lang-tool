from app import app, db
from models import Language, Word, Definition, WordClassifier
import views
import util

db.create_tables([
    Language, Word, Definition, WordClassifier
])

app.run()
