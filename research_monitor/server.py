"""Loopback-only dashboard server. Private snapshots are outside static assets."""
import argparse, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

STATIC=Path(__file__).with_name('static')

def make_handler(directory):
    directory=Path(directory)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Host','').split(':')[0] not in ('127.0.0.1','localhost'):
                self.send_error(403);return
            path=urlsplit(self.path).path
            if path=='/api/lanes':
                lanes=[]
                for name in ['nas-pullback','nas-breakout','spx-breakout','spx-pullback']:
                    try:
                        value=json.loads((directory/'lanes'/name/'state.json').read_text(encoding='utf-8'))
                        lanes.append(dict(value,lane_id=name))
                    except (OSError,ValueError):pass
                payload=json.dumps({'lanes':lanes},allow_nan=False).encode();mime='application/json'
            elif path in ('/api/state','/api/replays'):
                file=directory/('state.json' if path=='/api/state' else 'replays.json')
                fallback={'status':'idle','mode':'observed','candles':[],'events':[]} if path=='/api/state' else {'runs':[]}
                try:data=json.loads(file.read_text(encoding='utf-8'))
                except (OSError,ValueError):data=fallback
                payload=json.dumps(data,allow_nan=False).encode();mime='application/json'
            else:
                name={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css'}.get(path)
                if name is None:self.send_error(404);return
                payload=(STATIC/name).read_bytes();mime={'html':'text/html','js':'text/javascript','css':'text/css'}[name.split('.')[-1]]
            self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:")
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*args):pass
    return Handler

def main():
    parser=argparse.ArgumentParser(description='Local Atlas research monitor')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--state-dir',type=Path,default=Path(__file__).resolve().parents[1]/'local-results/research-monitor')
    args=parser.parse_args();server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(args.state_dir))
    print(f'Atlas monitor: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()

