# تك عربي — معالج الصور 📸

تطبيق ويب لمعالجة الصور تلقائياً: فلترة + تحسين + شعار.

---

## الميزات

- 📤 رفع صور متعددة (Drag & Drop)
- 🔍 فلترة الصور المهزوزة والمكررة
- ✨ تحسين الألوان والحدة
- 🏷️ إضافة شعار تك عربي تلقائياً
- 📦 تحميل النتائج كـ ZIP
- ☁️ رفع على Google Drive

---

## التشغيل المحلي

```bash
pip install -r requirements.txt
python app.py
```

افتح: http://localhost:5000

---

## النشر على Railway

### 1. اضغط Deploy on Railway
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app)

### 2. ربط GitHub Repo
- ارفع المشروع على GitHub
- في Railway: New Project → Deploy from GitHub

### 3. Environment Variables
أضف في Railway → Settings → Variables:

```
GOOGLE_CREDENTIALS_B64=<base64 credentials>
SECRET_KEY=<random string>
```

---

## إعداد Google Drive (اختياري)

### 1. إنشاء Service Account
1. اذهب إلى [Google Cloud Console](https://console.cloud.google.com)
2. APIs & Services → Credentials → Create Service Account
3. حمّل ملف JSON

### 2. تفعيل Google Drive API
1. APIs & Services → Library
2. ابحث عن "Google Drive API" → Enable

### 3. تحويل credentials لـ Base64
```bash
base64 -i credentials.json | tr -d '\n'
```

الصق الناتج في متغير `GOOGLE_CREDENTIALS_B64`

---

## هيكل المشروع

```
├── app.py                 # Flask backend
├── watermark_module.py    # إضافة الشعار
├── enhance_module.py      # تحسين الصور
├── filter_module.py       # فلترة المهزوزة والمكررة
├── logo.png               # شعار تك عربي
├── templates/
│   └── index.html         # الواجهة
├── static/
│   └── logo.png
├── requirements.txt
├── Dockerfile
└── railway.toml
```

---

## API Endpoints

| Method | Endpoint | الوظيفة |
|--------|----------|---------|
| GET | `/` | الصفحة الرئيسية |
| POST | `/upload` | رفع ومعالجة الصور |
| GET | `/preview/<session>/<cat>/<file>` | معاينة صورة |
| GET | `/download/<session>/<file>` | تحميل صورة |
| GET | `/download-all/<session>` | تحميل ZIP |
| POST | `/upload-drive/<session>` | رفع على Drive |
