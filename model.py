from google.appengine.ext import db
import hashlib

class Hash(db.StringProperty):
    pass

def gethash(data):
    return hashlib.sha512(data).hexdigest()

class Document(db.Model):
    url = db.LinkProperty(required=True)
    url_hash = Hash(required=True)
    last_version = db.BlobProperty()
    last_version_hash = Hash()

class WordRecord(db.Model):
    doc = db.ReferenceProperty(reference_class=Document, required=True)
    abs_wordcount = db.IntegerProperty(required=True)
    change_wordcount = db.IntegerProperty(required=True)
    timestamp = db.DateTimeProperty(required=True, auto_now=True)
