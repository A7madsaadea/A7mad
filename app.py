import os
import shutil
import zipfile
import json
import base64
import threading
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False

from filter_module import ImageFilter
from enhance_module import ImageEnhancer
from watermark_module import Watermarker

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

BASE_DIR     = Path(__file__).parent
LOGO_PATH    = str(BASE_DIR / "logo.png")
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {'.jpg', '.jpeg', '.png'}
MAX_WORKERS  = 4

# ── In-memory job store ────────────────────────────────────────────────────
# { job_id: { status, progress, total, results, session_id } }
JOBS = {}
JOBS_LOCK = threading.Lock()

def allowed(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXT

def get_session_dir(session_id):
    d = SESSIONS_DIR / session_id
    for sub in ['INPUT', 'FINAL', 'REJECTED', 'DUPLICATES']:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d

def process_one(name, session_dir, img_filter, results, lock, job_id):
    src = str(session_dir / 'INPUT' / name)
    _enhancer    = ImageEnhancer()
    _watermarker = Watermarker(LOGO_PATH)

    if img_filter.is_blurry(src):
        shutil.copy(src, str(session_dir / 'REJECTED' / name))
        with lock:
            results['rejected'].append(name)
    else:
        enhanced = _enhancer.process(src)
        if enhanced:
            final = _watermarker.apply(enhanced)
            out_path = str(session_dir / 'FINAL' / name)
            final.save(out_path, quality=95)
            with lock:
                results['final'].append(name)
        else:
            shutil.copy(src, str(session_dir / 'REJECTED' / name))
            with lock:
                results['rejected'].append(name)

    # Update progress
    with JOBS_LOCK:
        JOBS[job_id]['progress'] += 1

def run_job(job_id, session_id, saved):
    """Runs in a background thread. Updates JOBS dict."""
    session_dir = get_session_dir(session_id)
    img_filter  = ImageFilter(blur_threshold=100, hash_cutoff=5)
    results     = {'final': [], 'rejected': [], 'duplicates': []}
    lock        = threading.Lock()

    try:
        # Serial duplicate check
        non_dupes = []
        for name in saved:
            src = str(session_dir / 'INPUT' / name)
            if img_filter.is_duplicate(src):
                shutil.copy(src, str(session_dir / 'DUPLICATES' / name))
                results['duplicates'].append(name)
                with JOBS_LOCK:
                    JOBS[job_id]['progress'] += 1
            else:
                non_dupes.append(name)

        # Parallel process
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(process_one, name, session_dir,
                                img_filter, results, lock, job_id): name
                for name in non_dupes
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    name = futures[future]
                    print(f"Error {name}: {e}")
                    with lock:
                        results['rejected'].append(name)
                    with JOBS_LOCK:
                        JOBS[job_id]['progress'] += 1

        with JOBS_LOCK:
            JOBS[job_id].update({
                'status':  'done',
                'results': results,
                'stats': {
                    'total':      len(saved),
                    'final':      len(results['final']),
                    'rejected':   len(results['rejected']),
                    'duplicates': len(results['duplicates']),
                }
            })

    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]['status'] = 'error'
            JOBS[job_id]['error']  = str(e)


# ── Routes ─────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('images')
    if not files:
        return jsonify({'error': 'No files uploaded'}), 400

    session_id  = uuid.uuid4().hex
    job_id      = uuid.uuid4().hex
    session_dir = get_session_dir(session_id)

    saved = []
    for f in files:
        if f and allowed(f.filename):
            name = secure_filename(f.filename)
            dest = session_dir / 'INPUT' / name
            f.save(str(dest))
            saved.append(name)

    if not saved:
        return jsonify({'error': 'No valid image files'}), 400

    # Register job
    with JOBS_LOCK:
        JOBS[job_id] = {
            'status':     'processing',
            'session_id': session_id,
            'total':      len(saved),
            'progress':   0,
            'results':    None,
            'stats':      None,
        }

    # Start background thread — return immediately
    t = threading.Thread(target=run_job, args=(job_id, session_id, saved),
                         daemon=True)
    t.start()

    return jsonify({'job_id': job_id, 'total': len(saved)})


@app.route('/status/<job_id>')
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@app.route('/preview/<session_id>/<category>/<filename>')
def preview(session_id, category, filename):
    category = category.upper()
    if category not in ('FINAL', 'REJECTED', 'DUPLICATES'):
        return 'Invalid category', 400
    path = SESSIONS_DIR / session_id / category / secure_filename(filename)
    if not path.exists():
        return 'Not found', 404
    return send_file(str(path))


@app.route('/download/<session_id>/<filename>')
def download_one(session_id, filename):
    path = SESSIONS_DIR / session_id / 'FINAL' / secure_filename(filename)
    if not path.exists():
        return 'Not found', 404
    return send_file(str(path), as_attachment=True)


@app.route('/download-all/<session_id>')
def download_all(session_id):
    final_dir = SESSIONS_DIR / session_id / 'FINAL'
    if not final_dir.exists():
        return 'Session not found', 404
    zip_path = SESSIONS_DIR / session_id / 'final_images.zip'
    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        for img in final_dir.iterdir():
            zf.write(str(img), img.name)
    return send_file(str(zip_path), as_attachment=True,
                     download_name='TechArabi_Processed.zip')


@app.route('/upload-drive/<session_id>', methods=['POST'])
def upload_drive(session_id):
    if not DRIVE_AVAILABLE:
        return jsonify({'error': 'Google Drive library not installed'}), 500
    creds_b64 = os.environ.get('GOOGLE_CREDENTIALS_B64')
    if not creds_b64:
        return jsonify({'error': 'Google Drive credentials not configured'}), 500
    try:
        creds_json = json.loads(base64.b64decode(creds_b64))
        creds = service_account.Credentials.from_service_account_info(
            creds_json, scopes=['https://www.googleapis.com/auth/drive.file'])
        service   = build('drive', 'v3', credentials=creds)
        from datetime import date
        folder_name = f"TechArabi-Processed-{date.today()}"
        folder    = service.files().create(
            body={'name': folder_name,
                  'mimeType': 'application/vnd.google-apps.folder'},
            fields='id').execute()
        folder_id = folder['id']
        final_dir = SESSIONS_DIR / session_id / 'FINAL'
        uploaded  = []
        for img_path in final_dir.iterdir():
            media = MediaFileUpload(str(img_path), mimetype='image/jpeg')
            service.files().create(
                body={'name': img_path.name, 'parents': [folder_id]},
                media_body=media, fields='id').execute()
            uploaded.append(img_path.name)
        service.permissions().create(
            fileId=folder_id,
            body={'type': 'anyone', 'role': 'reader'}).execute()
        return jsonify({
            'url': f"https://drive.google.com/drive/folders/{folder_id}",
            'uploaded': len(uploaded)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
