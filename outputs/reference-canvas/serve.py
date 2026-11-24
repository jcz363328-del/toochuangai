from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
root=Path(__file__).parent/'build'
class Handler(SimpleHTTPRequestHandler):
 def translate_path(self,path):
  name=path.split('?',1)[0].removeprefix('/infinite-canvas/').lstrip('/')
  target=root/name
  return str(target if target.is_file() else root/'index.html')
ThreadingHTTPServer(('127.0.0.1',18614),Handler).serve_forever()
