from app import app, db
from models import Language, Word, WordClassifier
import views
import util

db.create_tables([
    Language, Word, WordClassifier
])

app.run()
