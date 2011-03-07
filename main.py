#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util, template
from google.appengine.api import taskqueue
from google.appengine.api.urlfetch import fetch
import logging
import zlib
import magic
from pdfminer.pdfparser import PDFDocument, PDFParser
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter, process_pdf
from pdfminer.pdfdevice import PDFDevice, TagExtractor
from pdfminer.converter import TextConverter
from pdfminer.cmapdb import CMapDB
from pdfminer.layout import LAParams
from StringIO import StringIO
import string
import re
import difflib

import model
import os


def queue_fetch(doc):
    """Added document to the queue for later fetching."""
    logging.info('Queuing document %s' % doc.url_hash)
    taskqueue.add(url='/tasks/fetchdoc', params={'url_hash' : doc.url_hash},
                  method='GET')

class MainHandler(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates/main.html')
        self.response.out.write(template.render(path, {}))
    def post(self):
        """Handle a new registration."""
        url = self.request.get('url')
        logging.info('Adding %s url' %url)
        url_hash = model.gethash(url)
        # Add new entry to the data
        doc = model.Document(url=url, url_hash=url_hash)
        doc.put()
        path = os.path.join(os.path.dirname(__file__), 'templates/newurl.html')
        self.response.out.write(template.render(path, {'url' : 'count?doc=%s' % url_hash}))
        # Add a task to fetch this document immediately.
        queue_fetch(doc)

class HourlyFetchHandler(webapp.RequestHandler):
    def get(self):
        logging.info('Hourly fetch')
        for doc in model.Document.all():
            queue_fetch(doc)

def get_pdf_text(content):
    """Extract the text of a pdf file."""
    outfp = StringIO()
    password = ''
    laparams = LAParams()
    codec = 'utf-8'
    pagenos = set()
    maxpages = 0
    rsrcmgr = PDFResourceManager(caching=False)
    device = TextConverter(rsrcmgr, outfp, codec=codec, laparams=laparams)
    content = StringIO(content)
    process_pdf(rsrcmgr, device, content, pagenos, maxpages=maxpages, password=password, check_extractable=True,
                caching=False)
    output = outfp.getvalue()
    # Try and free up memory
    outfp.close()
    content.close()
    return output

def get_text(content):
    """Extract text from a file (currently handles PDFs and plain text)."""
    type = magic.whatis(content)
    logging.info('Magic type %s' % type)
    if type == 'PDF document':
        text = get_pdf_text(content)
    else: # Assume its text
        text = content

    # Clean up the text as bit
    text = text.strip()
    text = string.join(re.split('\W+', text))
    return text

def get_word_stats(newtext, oldtext=None):
    """Calculate the absolute number of words in the next text and all the change from the old text.
    The text has already been cleaned up a bit (see get_text)."""
    # First the easy bit - absolute word count.
    abs_wc = len(string.split(newtext))
    change_wc = 0
    if oldtext != None:
        # Need to calculate how much the text has changed.
        # First split everything into lists
        newtext = string.split(newtext)
        oldtext = string.split(oldtext)
        last_change = None
        for c in difflib.Differ().compare(newtext, oldtext):
            linetype = c[0:2]
            if linetype == '+ ' or linetype == '- ':
                # This line marks a change (unless it is similar to a proceeding line in which case it
                # may not mark a change.
                thisline = c[2:]
                if last_change == None or difflib.get_close_matches(thisline, [last_change]) == []:
                    # This is a new change
                    last_change = thisline
                    change_wc += 1
                else: # Don't double count word changes
                    last_change = None
                
    return abs_wc, change_wc

def update_doc_stats(doc):
    """Get the absolute and changed words for the new document."""
    content = fetch(doc.url).content
    content_hash = model.gethash(content)
    logging.info('Acquired document hash:%s' % content_hash)
    # Check if the document has changed
    if content_hash == doc.last_version_hash:
        # No change to the document. Copy the old entry
        logging.info('No change to document')
        oldrec = model.WordRecord.all().filter('doc =', doc).order('-timestamp').get()
        # Save a new copy
        model.WordRecord(doc=doc, abs_wordcount=oldrec.abs_wordcount, change_wordcount=0).put()
    else:
        # The document has changed.
        # We need to run a comparision
        # Decompress old version
        if doc.last_version:
            last_version = zlib.decompress(doc.last_version) 
        else:
            last_version = None
        # Extract text out of new version
        logging.info('Document change. Calculating new stats')
        current_version = get_text(content)
        abs_wc, change = get_word_stats(current_version, last_version)
        # Add record
        model.WordRecord(doc=doc, abs_wordcount=abs_wc, change_wordcount=change).put() 
        # Update our version of the document.
        doc.last_version_hash = content_hash; doc.last_version = zlib.compress(current_version)
        doc.put()
    logging.info('Updated stats')


class FetchDocHandler(webapp.RequestHandler):
    def get(self):
        url_hash = self.request.get('url_hash')
        logging.info('Fetching %s' % url_hash)
        doc = model.Document.all().filter('url_hash =', url_hash).get()
        assert(doc)
        logging.info(doc)
        update_doc_stats(doc)

class DisplayHandler(webapp.RequestHandler):
    def get(self):
        doc = model.Document.all().filter('url_hash =', self.request.get('doc')).get()
        assert(doc)
        # Find the corresponding data entries for the document.
        record_list = model.WordRecord.all()
        path = os.path.join(os.path.dirname(__file__), 'templates/display.html')
        self.response.out.write(template.render(path, {'record_list' : record_list}))


def main():
    application = webapp.WSGIApplication([('/', MainHandler),
                                          ('/tasks/hourlyfetch', HourlyFetchHandler),
                                          ('/tasks/fetchdoc', FetchDocHandler),
                                          ('/count.*', DisplayHandler)],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
