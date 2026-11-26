import os, re, glob, shutil, tempfile
from flask import Flask, request, jsonify, send_file, send_from_directory, after_this_request
import yt_dlp

app = Flask(__name__)
ALLOWED = re.compile(r'^https?://([\w-]+\.)*(youtube\.com|youtu\.be|facebook\.com|fb\.watch|fb\.com)/', re.I)


def valid(u):
    return bool(u and ALLOWED.match(u))


@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    r.headers['Access-Control-Expose-Headers'] = 'Content-Disposition, Content-Length'
    return r


@app.get('/')
def home():
    return send_from_directory('.', 'index.html')


@app.route('/api/info', methods=['POST', 'OPTIONS'])
def info():
    if request.method == 'OPTIONS':
        return '', 204
    u = ((request.get_json(silent=True) or {}).get('url') or '').strip()
    if not valid(u):
        return jsonify(error='اللينك مش يوتيوب ولا فيسبوك'), 400
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True, 'skip_download': True}) as y:
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
    opts = {'quiet': True, 'noplaylist': True, 'outtmpl': os.path.join(tmp, '%(title).80s.%(ext)s')}
    if fmt == 'mp3':
        opts.update(format='bestaudio/best',
                    postprocessors=[{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': q}])
    else:
        opts.update(format=f'bestvideo[height<={q}]+bestaudio/best[height<={q}]/best', merge_output_format='mp4')
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([u])
        f = glob.glob(os.path.join(tmp, '*'))[0]
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        return 'failed', 500

    @after_this_request
    def clean(r):
        shutil.rmtree(tmp, ignore_errors=True)
        return r

    return send_file(f, as_attachment=True)


if __name__ == '__main__':
    app.run(port=5000)
