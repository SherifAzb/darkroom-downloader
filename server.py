import os, re, glob, shutil, tempfile
from flask import Flask, request, jsonify, send_file, send_from_directory, after_this_request
import yt_dlp
from flask import Flask, request, jsonify, send_file, send_from_directory, after_this_request
import yt_dlp

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4096
TOKEN = os.environ.get('ACCESS_TOKEN', '')
MAX_BYTES = 150 * 1024 * 1024
MAX_SECONDS = 20 * 60
SLOTS = threading.Semaphore(2)
HITS = {}


def too_many(ip, limit=20, window=600):
    now = time.time()
    h = [t for t in HITS.get(ip, []) if now - t < window]
    h.append(now)
    HITS[ip] = h
    if len(HITS) > 5000:
        HITS.clear()
    return len(h) > limit


@app.before_request
def guard():
    if not request.path.startswith('/api/') or request.method == 'OPTIONS':
        return None
    if request.headers.get('Origin', '') not in ORIGINS and request.headers.get('Sec-Fetch-Site', '') != 'same-origin':
        return jsonify(error='forbidden'), 403
    if TOKEN and request.headers.get('X-Token', '') != TOKEN and request.args.get('t', '') != TOKEN:
        return jsonify(error='forbidden'), 403
    ip = (request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0]).strip()
    if too_many(ip):
        return jsonify(error='طلبات كتير، استنى شوية.'), 429
    return None
ALLOWED = re.compile(r'^https?://([\w-]+\.)*(youtube\.com|youtu\.be|facebook\.com|fb\.watch|fb\.com)/', re.I)


ORIGINS = {'https://sherifazb.github.io', 'http://localhost:5000', 'http://127.0.0.1:5000', 'null'}


def valid(u):
    return bool(u and ALLOWED.match(u))


@app.after_request
def cors(r):
    o = request.headers.get('Origin', '')
    if o in ORIGINS:
        r.headers['Access-Control-Allow-Origin'] = o
        r.headers['Vary'] = 'Origin'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Token'
    r.headers['Access-Control-Allow-Private-Network'] = 'true'
    r.headers['Access-Control-Expose-Headers'] = 'Content-Disposition, Content-Length'
    return r


@app.get('/')
def home():
    return 'darkroom backend ok'


@app.get('/health')
def health():
    return jsonify(ok=True, yt_dlp=yt_dlp.version.__version__)


@app.route('/api/info', methods=['POST', 'OPTIONS'])
def info():
    if request.method == 'OPTIONS':
        return '', 204
    u = ((request.get_json(silent=True) or {}).get('url') or '').strip()
    if not valid(u):
        return jsonify(error='اللينك مش يوتيوب ولا فيسبوك'), 400
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True, 'skip_download': True, 'socket_timeout': 20}) as y:
            d = y.extract_info(u, download=False)
    except Exception:
        return jsonify(error='معرفتش أقرا اللينك ده، جرب لينك تاني'), 422
    return jsonify(title=d.get('title'), thumbnail=d.get('thumbnail'),
                   duration=d.get('duration'), uploader=d.get('uploader'))


@app.get('/api/download')
def download():
    u = request.args.get('url', '').strip()
    fmt = request.args.get('fmt', 'mp3')
    q = request.args.get('q', '')
    if not valid(u) or not q.isdigit():
        return 'bad request', 400
    tmp = tempfile.mkdtemp()
    opts = {'quiet': True, 'noplaylist': True, 'socket_timeout': 20, 'max_filesize': MAX_BYTES, 'match_filter': yt_dlp.utils.match_filter_func(f'duration < {MAX_SECONDS}'), 'outtmpl': os.path.join(tmp, '%(title).80s.%(ext)s')}
    if fmt == 'mp3':
        opts.update(format='bestaudio/best',
                    postprocessors=[{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': q}])
    else:
        opts.update(format=f'bestvideo[height<={q}]+bestaudio/best[height<={q}]/best', merge_output_format='mp4')
    if not SLOTS.acquire(blocking=False):
        shutil.rmtree(tmp, ignore_errors=True)
        return 'busy', 503
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([u])
        f = glob.glob(os.path.join(tmp, '*'))[0]
        if os.path.getsize(f) > MAX_BYTES:
            raise ValueError('too big')
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        return 'failed', 500
    finally:
        SLOTS.release()

    @after_this_request
    def clean(r):
        shutil.rmtree(tmp, ignore_errors=True)
        return r

    return send_file(f, as_attachment=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
