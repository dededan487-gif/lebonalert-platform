"""
LeBonAlert Platform - Version SIMPLE 100% Railway - Fix 404 /
"""
import os, json, sqlite3, uuid, requests, re
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session, g, send_file
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', 'lebonalert-simple-secret-' + str(uuid.uuid4()))
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
CORS(app, supports_credentials=True)

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'platform.db')
LEBONCOIN_API = "https://api.leboncoin.fr/finder/search"
LEBONCOIN_API_KEY = os.environ.get('LEBONCOIN_API_KEY', 'ba0c2dad52b3ec')

CATEGORIES = [
    {"id": "", "label": "🌐 Toutes catégories", "group": "Tout"},
    {"id": "2", "label": "🚗 Voitures", "group": "Véhicules"},
    {"id": "3", "label": "🏍️ Motos", "group": "Véhicules"},
    {"id": "9", "label": "🏠 Ventes immobilières", "group": "Immobilier"},
    {"id": "10", "label": "🏢 Locations", "group": "Immobilier"},
    {"id": "15", "label": "💻 Informatique", "group": "Multimédia"},
    {"id": "19", "label": "🛋️ Ameublement", "group": "Maison"},
    {"id": "33", "label": "💼 Offres d'emploi", "group": "Emploi"},
    {"id": "38", "label": "📦 Autres", "group": "Autres"},
]

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        telegram_chat_id TEXT,
        telegram_enabled INTEGER DEFAULT 0,
        email_enabled INTEGER DEFAULT 1,
        created_at TEXT,
        is_active INTEGER DEFAULT 1,
        is_premium INTEGER DEFAULT 1,
        is_admin INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        keywords TEXT NOT NULL,
        category_id TEXT DEFAULT '',
        description TEXT DEFAULT '',
        price_min INTEGER,
        price_max INTEGER,
        frequency INTEGER DEFAULT 60,
        active INTEGER DEFAULT 1,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS seen_ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        leboncoin_id TEXT NOT NULL,
        ad_data TEXT,
        found_at TEXT,
        UNIQUE(alert_id, leboncoin_id)
    )""")
    db.commit()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    if count == 0:
        print("📝 Création admin par défaut: admin / admin123")
        cur.execute("INSERT INTO users (username, email, password_hash, created_at, is_admin, is_premium, email_enabled) VALUES (?, ?, ?, ?, 1, 1, 1)",
                    ("admin", "admin@lebonalert.fr", generate_password_hash("admin123"), datetime.now().isoformat()))
        db.commit()
    db.close()
    print(f"✅ DB OK at {DB_PATH} - frontend at {FRONTEND_DIR}")

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if 'user_id' not in session:
        return None
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    row = cur.fetchone()
    if row:
        return dict(row)
    return None

def search_leboncoin(keywords, category_id="", filters=None, limit=35):
    if filters is None:
        filters = {}
    body = {
        "limit": limit,
        "limit_alu": 3,
        "offset": 0,
        "filters": {
            "keywords": {"text": keywords},
            "enums": {"ad_type": ["offer"]}
        },
        "sort_by": "time",
        "sort_order": "desc"
    }
    if category_id and category_id.strip() != "":
        body["filters"]["category"] = {"id": category_id.strip()}
    price_filter = {}
    if filters.get("price_min"):
        try: price_filter["min"] = int(filters["price_min"])
        except: pass
    if filters.get("price_max"):
        try: price_filter["max"] = int(filters["price_max"])
        except: pass
    if price_filter:
        body["filters"]["ranges"] = {"price": price_filter}
    headers = {
        "api_key": LEBONCOIN_API_KEY,
        "Content-Type": "application/json",
        "Origin": "https://www.leboncoin.fr",
        "Referer": "https://www.leboncoin.fr/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*"
    }
    try:
        resp = requests.post(LEBONCOIN_API, headers=headers, json=body, timeout=15)
        if resp.status_code != 200:
            return {"error": "captcha" if "captcha" in resp.text.lower() else "http", "ads": []}
        data = resp.json()
        ads = data.get("ads", [])
        normalized = []
        for ad in ads:
            normalized.append({
                "id": ad.get("list_id"),
                "subject": ad.get("subject"),
                "body": (ad.get("body") or "")[:400],
                "price": ad.get("price_cents") and ad.get("price_cents")//100 or ad.get("price"),
                "url": ad.get("url") or f"https://www.leboncoin.fr/cl/{ad.get('list_id')}.htm",
                "category_id": str(ad.get("category_id") or ""),
                "category_name": ad.get("category_name") or "Autre",
                "location": f"{ad.get('location',{}).get('city','')} ({ad.get('location',{}).get('zipcode','')})".strip(),
                "first_image": ad.get('images',{}).get('thumb_url') or (ad.get('images',{}).get('urls',[None])[0]),
                "creation_date": ad.get("creation_date"),
            })
        return {"ads": normalized, "total": len(normalized)}
    except Exception as e:
        return {"error": str(e), "ads": []}

# Routes
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    if not username or not email or not password:
        return jsonify({"error": "Champs requis"}), 400
    if len(password)<6:
        return jsonify({"error": "Mdp min 6"}), 400
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO users (username, email, password_hash, created_at, email_enabled, telegram_enabled, is_premium, is_admin) VALUES (?,?,?,?,?,?,?,?)",
                    (username, email, generate_password_hash(password), datetime.now().isoformat(), 1, 0, 1, 0))
        db.commit()
        user_id = cur.lastrowid
        session['user_id']=user_id
        session.permanent=True
        example_id = f"alert_{uuid.uuid4().hex[:8]}"
        cur.execute("INSERT INTO alerts (id, user_id, keywords, category_id, description, frequency, active, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (example_id, user_id, "clio 1983", "2", "Exemple", 60, 1, datetime.now().isoformat()))
        db.commit()
        return jsonify({"ok": True, "user": {"id": user_id, "username": username, "email": email}})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username ou email déjà pris"}),400

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    identifier = (data.get('username') or data.get('email') or '').strip()
    password = data.get('password') or ''
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE username=? OR email=?", (identifier, identifier.lower()))
    row = cur.fetchone()
    if not row or not check_password_hash(row['password_hash'], password):
        return jsonify({"error": "Identifiant ou mdp incorrect"}),401
    session['user_id']=row['id']
    session.permanent=True
    return jsonify({"ok": True, "user": {"id": row['id'], "username": row['username'], "email": row['email']}})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route('/api/auth/me', methods=['GET'])
def me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}),401
    return jsonify({"authenticated": True, "user": {"id": user['id'], "username": user['username'], "email": user['email'], "is_premium": True, "is_admin": bool(user['is_admin']), "plan": {"name":"Premium","badge":"⭐ Premium"}}})

@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify({"categories": CATEGORIES})

@app.route('/api/alerts', methods=['GET'])
@login_required
def list_alerts():
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC", (user['id'],))
    alerts = [dict(r) for r in cur.fetchall()]
    return jsonify({"alerts": alerts})

@app.route('/api/alerts', methods=['POST'])
@login_required
def create_alert():
    user = get_current_user()
    data = request.get_json() or {}
    if not data.get('keywords'):
        return jsonify({"error": "Mots-clés requis"}),400
    alert_id = f"alert_{uuid.uuid4().hex[:8]}"
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO alerts (id, user_id, keywords, category_id, description, price_min, price_max, frequency, active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (alert_id, user['id'], data['keywords'].strip(), str(data.get('category_id') or ""), (data.get('description') or "").strip(),
         int(data['price_min']) if data.get('price_min') else None,
         int(data['price_max']) if data.get('price_max') else None,
         int(data.get('frequency',60)), 1, datetime.now().isoformat()))
    db.commit()
    cur.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
    return jsonify({"ok": True, "alert": dict(cur.fetchone())})

@app.route('/api/alerts/<alert_id>', methods=['DELETE'])
@login_required
def delete_alert(alert_id):
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM alerts WHERE id=? AND user_id=?", (alert_id, user['id']))
    db.commit()
    return jsonify({"ok": True})

@app.route('/api/search', methods=['GET','POST'])
def api_search():
    if request.method=='GET':
        keywords=request.args.get('q','')
        category_id=request.args.get('category_id','')
    else:
        data=request.get_json() or {}
        keywords=data.get('keywords','')
        category_id=data.get('category_id') or ""
    if not keywords:
        return jsonify({"ads":[], "total":0})
    result=search_leboncoin(keywords, category_id, {})
    return jsonify(result)

@app.route('/health')
def health():
    return jsonify({"status":"ok", "time": datetime.now().isoformat(), "frontend": os.path.exists(os.path.join(FRONTEND_DIR, 'index.html'))})

@app.route('/')
def serve_front():
    index_path = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.exists(index_path):
        return send_file(index_path)
    else:
        return f"Frontend not found at {index_path}. Files: {os.listdir(FRONTEND_DIR) if os.path.exists(FRONTEND_DIR) else 'no frontend dir'}", 404

@app.route('/<path:path>')
def serve_static(path):
    # Try frontend folder
    fp = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(fp) and os.path.isfile(fp):
        return send_from_directory(FRONTEND_DIR, path)
    # For SPA, return index.html if no extension
    if '.' not in path.split('/')[-1]:
        index_path = os.path.join(FRONTEND_DIR, 'index.html')
        if os.path.exists(index_path):
            return send_file(index_path)
    return jsonify({"error": "not found", "path": path}), 404

init_db()

if __name__=='__main__':
    port=int(os.environ.get('PORT',5000))
    print(f"🚀 LeBonAlert SIMPLE sur port {port} - frontend: {FRONTEND_DIR} exists={os.path.exists(FRONTEND_DIR)}")
    if os.path.exists(FRONTEND_DIR):
        print(f"📁 Frontend files: {os.listdir(FRONTEND_DIR)[:10]}")
    app.run(host='0.0.0.0', port=port, debug=False)
