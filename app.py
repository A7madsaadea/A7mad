import os
import shutil
import zipfile
import json
import base64
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename

# Google Drive imports (optional - only if credentials exist)
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
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max upload

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
LOGO_PATH   = str(BASE_DIR / "logo.png")
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {'.jpg', '.jpeg', '.png'}

# ── Helpers ────────────────────────────────────────────────────────────────
def allowed(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXT

def get_session_dir(session_id):
    d = SESSIONS_DIR / session_id
    for sub in ['INPUT', 'FINAL', 'REJECTED', 'DUPLICATES']:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d

# ── Routes ─────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('images')
    if not files:
        return jsonify({'error': 'No files uploaded'}), 400

    import uuid
    session_id = uuid.uuid4().hex
    session_dir = get_session_dir(session_id)

    # Save uploads
    saved = []
    for f in files:
        if f and allowed(f.filename):
            name = secure_filename(f.filename)
            dest = session_dir / 'INPUT' / name
            f.save(str(dest))
            saved.append(name)

    if not saved:
        return jsonify({'error': 'No valid image files'}), 400

    # Process
    img_filter  = ImageFilter(blur_threshold=100, hash_cutoff=5)
    enhancer    = ImageEnhancer()
    watermarker = Watermarker(LOGO_PATH)

    results = {'final': [], 'rejected': [], 'duplicates': []}

    for name in saved:
        src = str(session_dir / 'INPUT' / name)

        if img_filter.is_blurry(src):
            shutil.copy(src, str(session_dir / 'REJECTED' / name))
            results['rejected'].append(name)
            continue

        if img_filter.is_duplicate(src):
            shutil.copy(src, str(session_dir / 'DUPLICATES' / name))
            results['duplicates'].append(name)
            continue

        enhanced = enhancer.process(src)
        if enhanced:
            final = watermarker.apply(enhanced)
            out_path = str(session_dir / 'FINAL' / name)
            final.save(out_path, quality=95)
            results['final'].append(name)
        else:
            results['rejected'].append(name)

    return jsonify({
        'session_id': session_id,
        'results': results,
        'stats': {
            'total':      len(saved),
            'final':      len(results['final']),
            'rejected':   len(results['rejected']),
            'duplicates': len(results['duplicates']),
        }
    })


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
    with zipfile.ZipFile(str(zip_path), 'w') as zf:
        for img in final_dir.iterdir():
            zf.write(str(img), img.name)

    return send_file(str(zip_path), as_attachment=True, download_name='TechArabi_Processed.zip')


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
            creds_json,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        service = build('drive', 'v3', credentials=creds)

        # Create dated folder
        from datetime import date
        folder_name = f"TechArabi-Processed-{date.today()}"
        folder_meta = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=folder_meta, fields='id').execute()
        folder_id = folder['id']

        # Upload FINAL images
        final_dir = SESSIONS_DIR / session_id / 'FINAL'
        uploaded = []
        for img_path in final_dir.iterdir():
            media = MediaFileUpload(str(img_path), mimetype='image/jpeg')
            file_meta = {'name': img_path.name, 'parents': [folder_id]}
            service.files().create(body=file_meta, media_body=media, fields='id').execute()
            uploaded.append(img_path.name)

        # Make folder publicly viewable
        service.permissions().create(
            fileId=folder_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        drive_url = f"https://drive.google.com/drive/folders/{folder_id}"
        return jsonify({'url': drive_url, 'uploaded': len(uploaded)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
