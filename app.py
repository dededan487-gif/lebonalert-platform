"""
LeBonAlert Platform v5 - SaaS Multi-User + Stripe Premium + Admin Panel
- Freemium: Gratuit 3 alertes max, 5min min, Email seulement
- Premium 4.99€/mois: illimité, 30s, Telegram+Email
- Admin panel: gestion users, stats, make premium
- Stripe Checkout + Webhook + Customer Portal

ENV nécessaires:
SECRET_KEY, TELEGRAM_BOT_TOKEN, SMTP_*, STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_PRICE_ID, STRIPE_WEBHOOK_SECRET
"""
import os, json, sqlite3, uuid, threading, time, requests, re
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='frontend', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'lebonalert-secret-key-change-in-prod-' + str(uuid.uuid4()))
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
CORS(app, supports_credentials=True)

# --- Config ---
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'platform.db')
LEBONCOIN_API = "https://api.leboncoin.fr/finder/search"
LEBONCOIN_API_KEY = os.environ.get('LEBONCOIN_API_KEY', 'ba0c2dad52b3ec')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN', '')

# Stripe
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID', '')  # price_xxx mensuel 4.99€
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# SMTP
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
SMTP_FROM = os.environ.get('SMTP_FROM', 'alertes@lebonalert.fr')

# Plans
PLANS = {
    "free": {
        "name": "Gratuit",
        "price": 0,
        "max_alerts": 3,
        "min_frequency": 300,  # 5 min
        "can_telegram": False,
        "can_email": True,
        "badge": "🆓 Gratuit"
    },
    "premium": {
        "name": "Premium",
        "price": 4.99,
        "currency": "EUR",
        "interval": "mois",
        "max_alerts": 999,
        "min_frequency": 30,
        "can_telegram": True,
        "can_email": True,
        "badge": "⭐ Premium"
    }
}

# --- Catégories ---
CATEGORIES = [
    {"id": "", "label": "🌐 Toutes catégories", "group": "Tout"},
    {"id": "2", "label": "🚗 Voitures", "group": "Véhicules"},
    {"id": "3", "label": "🏍️ Motos", "group": "Véhicules"},
    {"id": "4", "label": "🚐 Caravaning", "group": "Véhicules"},
    {"id": "5", "label": "🚚 Utilitaires", "group": "Véhicules"},
    {"id": "300", "label": "🚛 Camions", "group": "Véhicules"},
    {"id": "7", "label": "⛵ Nautisme", "group": "Véhicules"},
    {"id": "55", "label": "🚲 Vélos", "group": "Véhicules"},
    {"id": "6", "label": "🔧 Equipement Auto", "group": "Véhicules"},
    {"id": "44", "label": "🏍️ Equipement Moto", "group": "Véhicules"},
    {"id": "9", "label": "🏠 Ventes immobilières", "group": "Immobilier"},
    {"id": "10", "label": "🏢 Locations", "group": "Immobilier"},
    {"id": "11", "label": "👥 Colocations", "group": "Immobilier"},
    {"id": "12", "label": "🏖️ Locations vacances", "group": "Immobilier"},
    {"id": "13", "label": "🏬 Bureaux & Commerces", "group": "Immobilier"},
    {"id": "15", "label": "💻 Informatique", "group": "Multimédia"},
    {"id": "16", "label": "📷 Image & Son", "group": "Multimédia"},
    {"id": "17", "label": "📱 Téléphonie", "group": "Multimédia"},
    {"id": "43", "label": "🎮 Consoles & Jeux vidéo", "group": "Multimédia"},
    {"id": "19", "label": "🛋️ Ameublement", "group": "Maison"},
    {"id": "20", "label": "🔌 Electroménager", "group": "Maison"},
    {"id": "21", "label": "🔨 Bricolage", "group": "Maison"},
    {"id": "22", "label": "👕 Vêtements", "group": "Maison"},
    {"id": "39", "label": "🎨 Décoration", "group": "Maison"},
    {"id": "52", "label": "🌿 Jardinage", "group": "Maison"},
    {"id": "27", "label": "📚 Livres", "group": "Loisirs"},
    {"id": "28", "label": "🐾 Animaux", "group": "Loisirs"},
    {"id": "29", "label": "⚽ Sports & Hobbies", "group": "Loisirs"},
    {"id": "40", "label": "🏺 Collection", "group": "Loisirs"},
    {"id": "41", "label": "🧸 Jeux & Jouets", "group": "Loisirs"},
    {"id": "42", "label": "💍 Montres & Bijoux", "group": "Loisirs"},
    {"id": "33", "label": "💼 Offres d'emploi", "group": "Emploi & Services"},
    {"id": "34", "label": "🤝 Prestations services", "group": "Emploi & Services"},
    {"id": "32", "label": "🏭 Matériel Pro", "group": "Pro"},
    {"id": "57", "label": "🚜 Matériel Agricole", "group": "Pro"},
    {"id": "38", "label": "📦 Autres", "group": "Autres"},
]

# --- DB ---
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
        is_premium INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
        premium_until TEXT
    )""")
    # Ajoute colonnes si ancienne DB
    cur.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cur.fetchall()]
    if 'is_premium' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
    if 'is_admin' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    if 'stripe_customer_id' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")
    if 'stripe_subscription_id' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT")
    if 'premium_until' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN premium_until TEXT")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        keywords TEXT NOT NULL,
        category_id TEXT DEFAULT '',
        description TEXT DEFAULT '',
        price_min INTEGER,
        price_max INTEGER,
        location_mode TEXT DEFAULT 'france',
        departments TEXT,
        regions TEXT,
        city TEXT,
        radius INTEGER,
        frequency INTEGER DEFAULT 60,
        active INTEGER DEFAULT 1,
        notify_email INTEGER DEFAULT 1,
        notify_telegram INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT,
        new_count INTEGER DEFAULT 0,
        total_found INTEGER DEFAULT 0,
        last_checked_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS seen_ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        leboncoin_id TEXT NOT NULL,
        ad_data TEXT,
        found_at TEXT,
        notified_email INTEGER DEFAULT 0,
        notified_telegram INTEGER DEFAULT 0,
        UNIQUE(alert_id, leboncoin_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS checker_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id TEXT,
        checked_at TEXT,
        found_count INTEGER,
        new_count INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        stripe_session_id TEXT,
        stripe_subscription_id TEXT,
        amount INTEGER,
        currency TEXT,
        status TEXT,
        created_at TEXT
    )""")
    db.commit()
    # Premier admin si aucun user
     cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()[0] == 0:
        print("📝 Aucun user, création admin par défaut: admin / admin123")
        cur.execute("INSERT INTO users (username, email, password_hash, created_at, is_admin, is_premium, email_enabled) VALUES (?, ?, ?, ?, 1, 1, 1)",
                    ("admin", "admin@lebonalert.fr", generate_password_hash("admin123"), datetime.now().isoformat()))
        db.commit()
    db.close()
    print(f"✅ DB init at {DB_PATH} - Plans: Free 3 alertes / Premium illimité")

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- Helpers Premium ---
def is_premium_user(user):
    if not user:
        return False
    if user.get('is_admin'):  # admin toujours premium
        return True
    if user.get('is_premium'):
        # Vérifie expiration
        until = user.get('premium_until')
        if until:
            try:
                if datetime.fromisoformat(until) < datetime.now():
                    return False
            except:
                pass
        return True
    return False

def get_user_plan(user):
    if is_premium_user(user):
        return PLANS["premium"]
    return PLANS["free"]

def can_create_alert(user, db=None):
    """Free: max 3 alertes"""
    if is_premium_user(user):
        return True, ""
    if db is None:
        db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) as c FROM alerts WHERE user_id = ?", (user['id'],))
    count = cur.fetchone()['c']
    plan = PLANS["free"]
    if count >= plan["max_alerts"]:
        return False, f"Limite gratuite atteinte : {plan['max_alerts']} alertes max. Passe Premium à {PLANS['premium']['price']}€/mois pour illimité."
    return True, ""

def can_use_frequency(user, freq):
    plan = get_user_plan(user)
    if freq < plan["min_frequency"]:
        return False, f"Fréquence trop rapide. Plan {plan['name']}: minimum {plan['min_frequency']}s. Premium: 30s."
    return True, ""

def can_use_telegram(user):
    plan = get_user_plan(user)
    if not plan["can_telegram"]:
        return False, "Telegram réservé Premium. Passe à 4.99€/mois pour débloquer Telegram instantané."
    return True, ""

# --- Auth ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "not authenticated"}), 401
        user = get_current_user()
        if not user or not user.get('is_admin'):
            return jsonify({"error": "admin required"}), 403
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
        u = dict(row)
        # Parse bool
        u['is_premium'] = bool(u.get('is_premium'))
        u['is_admin'] = bool(u.get('is_admin'))
        # Check premium expiry
        if u.get('premium_until'):
            try:
                if datetime.fromisoformat(u['premium_until']) < datetime.now():
                    # Expired - downgrade
                    cur.execute("UPDATE users SET is_premium = 0 WHERE id = ?", (u['id'],))
                    db.commit()
                    u['is_premium'] = False
            except:
                pass
        return u
    return None

# --- Leboncoin Search ---
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
        "sort_by": filters.get("sort_by", "time"),
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
    if filters.get("departments"):
        depts = filters["departments"]
        if isinstance(depts, str):
            try: depts = json.loads(depts)
            except: depts = [depts]
        if depts:
            body["filters"]["location"] = {"departments": depts}
    headers = {
        "api_key": LEBONCOIN_API_KEY,
        "Content-Type": "application/json",
        "Origin": "https://www.leboncoin.fr",
        "Referer": "https://www.leboncoin.fr/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*"
    }
    try:
        resp = requests.post(LEBONCOIN_API, headers=headers, json=body, timeout=20)
        if resp.status_code != 200:
            if "captcha" in resp.text.lower():
                return {"error": "captcha", "message": "Captcha, pause 60s"}
            return {"error": "http", "status": resp.status_code, "message": resp.text[:300]}
        data = resp.json()
        ads = data.get("ads", [])
        normalized = []
        for ad in ads:
            attrs = {a["key"]: a.get("value_label") or a.get("value") for a in ad.get("attributes", [])}
            cat_name = ad.get("category_name") or next((c["label"] for c in CATEGORIES if c["id"] == str(ad.get("category_id") or "")), "Autre")
            normalized.append({
                "id": ad.get("list_id"),
                "subject": ad.get("subject"),
                "body": (ad.get("body") or "")[:500],
                "price": ad.get("price_cents") and ad.get("price_cents")//100 or ad.get("price"),
                "url": ad.get("url") or f"https://www.leboncoin.fr/cl/{ad.get('list_id')}.htm",
                "category_id": str(ad.get("category_id") or ""),
                "category_name": cat_name,
                "location": f"{ad.get('location',{}).get('city','')} ({ad.get('location',{}).get('zipcode','')})".strip(),
                "city": ad.get('location',{}).get('city'),
                "zipcode": ad.get('location',{}).get('zipcode'),
                "department": ad.get('location',{}).get('department_name'),
                "owner_type": ad.get('owner',{}).get('type'),
                "images": ad.get('images',{}).get('urls',[])[:3],
                "first_image": ad.get('images',{}).get('thumb_url') or (ad.get('images',{}).get('urls',[None])[0]),
                "creation_date": ad.get("creation_date"),
                "attributes": attrs,
            })
        return {"ads": normalized, "total": data.get("total", len(normalized))}
    except Exception as e:
        return {"error": "exception", "message": str(e)}

# --- Notifications ---
def send_email_notification(to_email, alert, ad, user):
    if not to_email:
        return False
    subject = f"🆕 {alert['keywords']} - {ad['subject'][:50]} - {ad.get('price','')}€"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f9fafb;padding:20px;border-radius:12px">
      <div style="background:white;border-radius:12px;padding:24px">
        <h2 style="color:#ff6a00">🔔 Nouvelle annonce !</h2>
        <p>Bonjour <b>{user['username']}</b>,</p>
        <p>Alerte <b>{alert['keywords']}</b> ({get_cat_label(alert['category_id'])}):</p>
        <div style="border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;margin:16px 0">
          {f'<img src="{ad["first_image"]}" style="width:100%;height:200px;object-fit:cover">' if ad.get('first_image') else ''}
          <div style="padding:14px">
            <h3 style="margin:0">{ad['subject']}</h3>
            <p style="font-size:20px;font-weight:bold;color:#ff6a00">{ad.get('price','N.C')} €</p>
            <p>📍 {ad.get('location','')} • 📂 {ad.get('category_name','')}</p>
            <p><a href="{ad['url']}" style="background:#111827;color:white;padding:10px 18px;border-radius:999px;text-decoration:none">Voir sur Leboncoin</a></p>
          </div>
        </div>
        <p style="font-size:11px;color:#999">Email Premium: {user['username']} - <a href="#">Gérer alertes</a></p>
      </div>
    </div>"""
    if SMTP_HOST and SMTP_USER:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = SMTP_FROM
            msg['To'] = to_email
            msg.attach(MIMEText(html, 'html'))
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
            server.quit()
            print(f"📧 Email to {to_email} ({alert['keywords']})")
            return True
        except Exception as e:
            print(f"Email fail: {e}")
    print(f"📧 [DEMO] Email to {to_email}: {subject}")
    with open(os.path.join(DATA_DIR, 'emails_demo.log'), 'a', encoding='utf-8') as f:
        f.write(f"[{datetime.now()}] TO:{to_email} ALERT:{alert['keywords']} AD:{ad['subject']}\n")
    return True

def send_telegram_notification(chat_id, alert, ad, user):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    try:
        price_txt = f"{ad.get('price')}€" if ad.get('price') else "N.C"
        location = ad.get('location') or ad.get('city') or 'France'
        text = f"""🔔 <b>{alert['keywords'].upper()}</b> - {get_cat_label(alert['category_id'])}

<b>{ad.get('subject','')}</b>

💰 <b>{price_txt}</b>
📍 {location}

<a href="{ad['url']}">👉 VOIR SUR LEBONCOIN</a>

<i>{user['username']} • {datetime.now().strftime('%H:%M')} • {PLANS['premium']['name'] if user.get('is_premium') else PLANS['free']['name']}</i>"""
        if ad.get('first_image'):
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                r = requests.post(url, json={"chat_id": chat_id, "photo": ad.get('first_image'), "caption": text, "parse_mode": "HTML"}, timeout=20)
                if r.status_code == 200:
                    print(f"✅ Telegram to {user['username']}: {ad['id']}")
                    return True
            except: pass
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram fail: {e}")
        return False

def get_cat_label(id):
    c = next((x for x in CATEGORIES if x["id"]==str(id)), None)
    return c["label"] if c else (id or "Toutes")

# --- Background Checker ---
checker_thread = None
checker_stop = False
checker_status = {"running": False, "last_loop": None, "total_checks": 0, "total_new": 0, "per_alert": {}, "global_status": "idle", "users_active": 0, "alerts_active": 0}

def background_checker():
    global checker_status, checker_stop
    checker_status["running"] = True
    print("🤖 Checker multi-user Premium démarré")
    while not checker_stop:
        try:
            db = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
            cur = db.cursor()
            cur.execute("""SELECT a.*, u.username, u.email, u.telegram_chat_id, u.telegram_enabled as user_telegram_enabled, u.email_enabled as user_email_enabled, u.is_premium, u.is_admin
                FROM alerts a JOIN users u ON a.user_id = u.id WHERE a.active=1 AND u.is_active=1""")
            rows = cur.fetchall()
            checker_status["alerts_active"] = len(rows)
            checker_status["users_active"] = len(set(r['user_id'] for r in rows))
            checker_status["last_loop"] = datetime.now().isoformat()
            if not rows:
                checker_status["global_status"] = "no active alerts"
                time.sleep(10)
                db.close()
                continue
            # Priorise premium: premium d'abord
            rows_sorted = sorted(rows, key=lambda r: (0 if r['is_premium'] or r['is_admin'] else 1, r['frequency']))
            for row in rows_sorted:
                if checker_stop: break
                alert = dict(row)
                alert_id = alert['id']
                frequency = alert['frequency'] or 60
                per = checker_status["per_alert"].get(alert_id, {})
                last_check_str = per.get('last_check')
                if last_check_str:
                    try:
                        elapsed = (datetime.now() - datetime.fromisoformat(last_check_str)).total_seconds()
                        if elapsed < frequency:
                            continue
                    except: pass
                filters = {
                    "price_min": alert['price_min'],
                    "price_max": alert['price_max'],
                    "departments": json.loads(alert['departments']) if alert['departments'] else None,
                }
                checker_status["per_alert"].setdefault(alert_id, {})['status'] = 'checking'
                checker_status["per_alert"][alert_id]['keywords'] = alert['keywords']
                checker_status["per_alert"][alert_id]['user'] = alert['username']
                
                result = search_leboncoin(alert['keywords'], alert['category_id'] or "", filters, limit=35)
                if "error" in result:
                    checker_status["per_alert"][alert_id]['status'] = f"error: {result.get('message','')[:50]}"
                    if result.get('error')=='captcha':
                        time.sleep(60)
                    continue
                
                ads = result.get('ads', [])
                cur.execute("SELECT leboncoin_id FROM seen_ads WHERE alert_id=?", (alert_id,))
                seen_ids = set(r[0] for r in cur.fetchall())
                is_first = len(seen_ids)==0
                new_ads = [ad for ad in ads if str(ad['id']) not in seen_ids]
                
                checker_status["per_alert"][alert_id]['last_check'] = datetime.now().isoformat()
                checker_status["per_alert"][alert_id]['last_count'] = len(ads)
                checker_status["per_alert"][alert_id]['last_new'] = len(new_ads) if not is_first else 0
                checker_status["per_alert"][alert_id]['status'] = 'ok'
                
                if new_ads:
                    if not is_first:
                        print(f"🆕 [{alert['username']}] [{alert['keywords']}] {len(new_ads)} nouvelles")
                        for ad in reversed(new_ads):
                            try:
                                cur.execute("INSERT OR IGNORE INTO seen_ads (alert_id, user_id, leboncoin_id, ad_data, found_at) VALUES (?,?,?,?,?)",
                                            (alert_id, alert['user_id'], str(ad['id']), json.dumps(ad, ensure_ascii=False), datetime.now().isoformat()))
                                db.commit()
                            except: pass
                            # Notifications
                            if alert['notify_email'] and alert['user_email_enabled'] and alert['email']:
                                if send_email_notification(alert['email'], alert, ad, alert):
                                    cur.execute("UPDATE seen_ads SET notified_email=1 WHERE alert_id=? AND leboncoin_id=?", (alert_id, str(ad['id'])))
                            if alert['notify_telegram'] and alert['user_telegram_enabled'] and alert['telegram_chat_id']:
                                # Vérifie si user premium pour telegram
                                if alert['is_premium'] or alert['is_admin'] or PLANS["free"]["can_telegram"]:
                                    if send_telegram_notification(alert['telegram_chat_id'], alert, ad, alert):
                                        cur.execute("UPDATE seen_ads SET notified_telegram=1 WHERE alert_id=? AND leboncoin_id=?", (alert_id, str(ad['id'])))
                            db.commit()
                            checker_status["total_new"]+=1
                    cur.execute("UPDATE alerts SET new_count=new_count+?, total_found=total_found+?, last_checked_at=?, updated_at=? WHERE id=?",
                                (len(new_ads) if not is_first else 0, len(new_ads), datetime.now().isoformat(), datetime.now().isoformat(), alert_id))
                    db.commit()
                    if is_first:
                        for ad in ads:
                            try:
                                cur.execute("INSERT OR IGNORE INTO seen_ads (alert_id, user_id, leboncoin_id, ad_data, found_at) VALUES (?,?,?,?,?)",
                                            (alert_id, alert['user_id'], str(ad['id']), json.dumps(ad, ensure_ascii=False), datetime.now().isoformat()))
                            except: pass
                        db.commit()
                else:
                    cur.execute("UPDATE alerts SET last_checked_at=? WHERE id=?", (datetime.now().isoformat(), alert_id))
                    db.commit()
                cur.execute("INSERT INTO checker_stats (alert_id, checked_at, found_count, new_count) VALUES (?,?,?,?)",
                            (alert_id, datetime.now().isoformat(), len(ads), len(new_ads) if not is_first else 0))
                db.commit()
                checker_status["total_checks"]+=1
                time.sleep(2)
            db.close()
            checker_status["global_status"]="ok"
            time.sleep(10)
        except Exception as e:
            print(f"Checker ex: {e}")
            import traceback; traceback.print_exc()
            checker_status["global_status"]=f"ex: {str(e)[:100]}"
            time.sleep(15)

def ensure_checker():
    global checker_thread
    if checker_thread is None or not checker_thread.is_alive():
        checker_thread = threading.Thread(target=background_checker, daemon=True)
        checker_thread.start()

# --- Auth Routes ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    if not username or not email or not password:
        return jsonify({"error": "username, email, password required"}), 400
    if len(password)<6:
        return jsonify({"error": "Mot de passe min 6 caractères"}), 400
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({"error": "Email invalide"}), 400
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        return jsonify({"error": "Username 3-20 alphanum _"}), 400
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO users (username, email, password_hash, created_at, email_enabled, telegram_enabled, is_premium, is_admin) VALUES (?,?,?,?,?,?,?,?)",
                    (username, email, generate_password_hash(password), datetime.now().isoformat(), 1, 0, 0, 0))
        db.commit()
        user_id = cur.lastrowid
        session['user_id']=user_id
        session.permanent=True
        # Exemple alerte
        example_id = f"alert_{uuid.uuid4().hex[:8]}"
        cur.execute("""INSERT INTO alerts (id, user_id, keywords, category_id, description, frequency, active, notify_email, notify_telegram, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (example_id, user_id, "clio 1983", "2", "Exemple - Ma première alerte", 300, 1, 1, 0, datetime.now().isoformat(), datetime.now().isoformat()))
        db.commit()
        return jsonify({"ok": True, "user": {"id": user_id, "username": username, "email": email}})
    except sqlite3.IntegrityError as e:
        err=str(e)
        if "username" in err: return jsonify({"error": "Username déjà pris"}),400
        if "email" in err: return jsonify({"error": "Email déjà utilisé"}),400
        return jsonify({"error": "Erreur inscription"}),400

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    identifier = (data.get('username') or data.get('email') or '').strip()
    password = data.get('password') or ''
    if not identifier or not password:
        return jsonify({"error": "Identifiant + mdp requis"}),400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE username=? OR email=?", (identifier, identifier.lower()))
    row = cur.fetchone()
    if not row or not check_password_hash(row['password_hash'], password):
        return jsonify({"error": "Identifiant ou mot de passe incorrect"}),401
    if not row['is_active']:
        return jsonify({"error": "Compte désactivé"}),403
    session['user_id']=row['id']
    session.permanent=True
    return jsonify({"ok": True, "user": {"id": row['id'], "username": row['username'], "email": row['email'], "telegram_chat_id": row['telegram_chat_id'], "telegram_enabled": bool(row['telegram_enabled']), "email_enabled": bool(row['email_enabled']), "is_premium": bool(row['is_premium']), "is_admin": bool(row['is_admin'])}})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route('/api/auth/me', methods=['GET'])
def me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}),401
    plan = get_user_plan(user)
    return jsonify({
        "authenticated": True,
        "user": {
            "id": user['id'],
            "username": user['username'],
            "email": user['email'],
            "telegram_chat_id": user['telegram_chat_id'],
            "telegram_enabled": bool(user['telegram_enabled']),
            "email_enabled": bool(user['email_enabled']),
            "is_premium": bool(user['is_premium']),
            "is_admin": bool(user['is_admin']),
            "premium_until": user.get('premium_until'),
            "plan": plan
        },
        "plans": PLANS,
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY if STRIPE_PUBLISHABLE_KEY else None
    })

# --- User Settings ---
@app.route('/api/user/settings', methods=['GET','PUT'])
@login_required
def user_settings():
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    if request.method=='GET':
        return jsonify({"user": {"username": user['username'], "email": user['email'], "telegram_chat_id": user['telegram_chat_id'], "telegram_enabled": bool(user['telegram_enabled']), "email_enabled": bool(user['email_enabled']), "is_premium": bool(user['is_premium']), "is_admin": bool(user['is_admin'])}})
    data = request.get_json() or {}
    telegram_chat_id = str(data.get('telegram_chat_id', user['telegram_chat_id'] or '')).strip()
    telegram_enabled = int(bool(data.get('telegram_enabled', user['telegram_enabled'])))
    email_enabled = int(bool(data.get('email_enabled', user['email_enabled'])))
    if telegram_chat_id and not re.match(r'^-?\d+$', telegram_chat_id):
        return jsonify({"error": "Telegram Chat ID numérique requis"}),400
    # Si user free veut activer telegram -> bloque
    if telegram_enabled and not is_premium_user(user):
        if not PLANS["free"]["can_telegram"]:
            return jsonify({"error": "Telegram réservé Premium (4.99€/mois). Passe Premium pour débloquer."}),403
    cur.execute("UPDATE users SET telegram_chat_id=?, telegram_enabled=?, email_enabled=? WHERE id=?", (telegram_chat_id or None, telegram_enabled, email_enabled, user['id']))
    db.commit()
    return jsonify({"ok": True})

@app.route('/api/user/test-telegram', methods=['POST'])
@login_required
def test_telegram_user():
    user = get_current_user()
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Bot Telegram non configuré serveur"}),400
    if not user['telegram_chat_id']:
        return jsonify({"error": "Configure Chat ID d'abord"}),400
    if not is_premium_user(user) and not PLANS["free"]["can_telegram"]:
        return jsonify({"error": "Telegram Premium uniquement"}),403
    data = request.get_json() or {}
    fake_ad = {"id":"test_123","subject":f"[TEST] {data.get('keywords','clio 1983')} - Test OK","price":2900,"location":"Besançon (25000)","url":"https://www.leboncoin.fr/","first_image":"https://images.unsplash.com/photo-1541899481282-d53bffe3c35d?w=600","category_name":"Test"}
    fake_alert = {"keywords": data.get('keywords','test'), "category_id":"", "id":"test"}
    ok = send_telegram_notification(user['telegram_chat_id'], fake_alert, fake_ad, user)
    return jsonify({"ok": ok, "message": "✅ Test envoyé !" if ok else "❌ Échec"})

@app.route('/api/user/test-email', methods=['POST'])
@login_required
def test_email_user():
    user = get_current_user()
    fake_ad = {"id":"test_123","subject":"[TEST] Email fonctionne !","price":2900,"location":"Besançon (25000)","category_name":"Voitures","url":"https://www.leboncoin.fr/","first_image":"https://images.unsplash.com/photo-1541899481282-d53bffe3c35d?w=600","creation_date":datetime.now().isoformat()}
    fake_alert = {"keywords":"clio 1983 test","id":"test","category_id":"2"}
    ok = send_email_notification(user['email'], fake_alert, fake_ad, user)
    return jsonify({"ok": ok, "message": f"✅ Email envoyé à {user['email']}"})

# --- Plans & Stripe ---
@app.route('/api/plans', methods=['GET'])
def get_plans():
    return jsonify({"plans": PLANS, "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY})

@app.route('/api/stripe/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    if not STRIPE_SECRET_KEY:
        return jsonify({"error": "Stripe non configuré (STRIPE_SECRET_KEY manquant). Mode démo: utilise /api/admin/make-premium"}),400
    user = get_current_user()
    if is_premium_user(user):
        return jsonify({"error": "Tu es déjà Premium"}),400
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        # Crée ou récupère customer
        customer_id = user.get('stripe_customer_id')
        if not customer_id:
            customer = stripe.Customer.create(email=user['email'], metadata={"user_id": user['id'], "username": user['username']})
            customer_id = customer.id
            db = get_db()
            db.cursor().execute("UPDATE users SET stripe_customer_id=? WHERE id=?", (customer_id, user['id']))
            db.commit()
        
        # Checkout session
        domain = request.headers.get('Origin') or request.host_url.rstrip('/')
        session_stripe = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}] if STRIPE_PRICE_ID else [{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": "LeBonAlert Premium - 4.99€/mois - Alertes illimitées + Telegram"},
                    "unit_amount": 499,
                    "recurring": {"interval": "month"}
                },
                "quantity": 1
            }],
            mode='subscription',
            success_url=domain + '/?premium=success',
            cancel_url=domain + '/?premium=cancel',
            metadata={"user_id": user['id']}
        )
        # Log payment
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO payments (user_id, stripe_session_id, amount, currency, status, created_at) VALUES (?,?,?,?,?,?)",
                    (user['id'], session_stripe.id, 499, 'eur', 'pending', datetime.now().isoformat()))
        db.commit()
        return jsonify({"ok": True, "url": session_stripe.url, "sessionId": session_stripe.id})
    except Exception as e:
        print(f"Stripe error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Stripe erreur: {str(e)}"}),500

@app.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    if not STRIPE_WEBHOOK_SECRET or not STRIPE_SECRET_KEY:
        return jsonify({"error": "Stripe non configuré"}),400
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        
        if event['type'] == 'checkout.session.completed':
            session_obj = event['data']['object']
            user_id = session_obj.get('metadata',{}).get('user_id')
            customer_id = session_obj.get('customer')
            subscription_id = session_obj.get('subscription')
            if user_id:
                db = sqlite3.connect(DB_PATH)
                cur = db.cursor()
                premium_until = (datetime.now() + timedelta(days=32)).isoformat()
                cur.execute("UPDATE users SET is_premium=1, stripe_customer_id=?, stripe_subscription_id=?, premium_until=? WHERE id=?",
                            (customer_id, subscription_id, premium_until, user_id))
                cur.execute("UPDATE payments SET status='completed', stripe_subscription_id=? WHERE stripe_session_id=?",
                            (subscription_id, session_obj['id']))
                db.commit()
                db.close()
                print(f"✅ Premium activé pour user {user_id} via Stripe")
        
        elif event['type'] == 'customer.subscription.deleted':
            sub = event['data']['object']
            customer_id = sub.get('customer')
            db = sqlite3.connect(DB_PATH)
            cur = db.cursor()
            cur.execute("UPDATE users SET is_premium=0 WHERE stripe_customer_id=?", (customer_id,))
            db.commit()
            db.close()
            print(f"❌ Abonnement annulé pour customer {customer_id}")
        
        elif event['type'] == 'invoice.payment_succeeded':
            invoice = event['data']['object']
            customer_id = invoice.get('customer')
            # Prolonge premium
            db = sqlite3.connect(DB_PATH)
            cur = db.cursor()
            cur.execute("SELECT id FROM users WHERE stripe_customer_id=?", (customer_id,))
            row = cur.fetchone()
            if row:
                premium_until = (datetime.now() + timedelta(days=32)).isoformat()
                cur.execute("UPDATE users SET is_premium=1, premium_until=? WHERE stripe_customer_id=?", (premium_until, customer_id))
                db.commit()
            db.close()
        
        return jsonify({"received": True})
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"error": str(e)}),400

@app.route('/api/stripe/portal', methods=['POST'])
@login_required
def customer_portal():
    if not STRIPE_SECRET_KEY:
        return jsonify({"error": "Stripe non configuré"}),400
    user = get_current_user()
    if not user.get('stripe_customer_id'):
        return jsonify({"error": "Pas d'abonnement"}),400
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        domain = request.headers.get('Origin') or request.host_url.rstrip('/')
        portal = stripe.billing_portal.Session.create(customer=user['stripe_customer_id'], return_url=domain)
        return jsonify({"url": portal.url})
    except Exception as e:
        return jsonify({"error": str(e)}),500

# --- Categories ---
@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify({"categories": CATEGORIES})

# --- Alerts ---
@app.route('/api/alerts', methods=['GET'])
@login_required
def list_alerts():
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC", (user['id'],))
    alerts = []
    for r in cur.fetchall():
        a = dict(r)
        try:
            if a['departments']: a['departments']=json.loads(a['departments'])
        except: pass
        try:
            if a['regions']: a['regions']=json.loads(a['regions'])
        except: pass
        alerts.append(a)
    return jsonify({"alerts": alerts, "plan": get_user_plan(user), "limits": {"can_create": can_create_alert(user, db)[0]}})

@app.route('/api/alerts', methods=['POST'])
@login_required
def create_alert_route():
    user = get_current_user()
    db = get_db()
    # Vérifie limites
    can, msg = can_create_alert(user, db)
    if not can:
        return jsonify({"error": msg, "upgrade_required": True}),403
    
    data = request.get_json() or {}
    if not data.get('keywords'):
        return jsonify({"error": "Mots-clés requis"}),400
    
    category_id = str(data.get('category_id') or data.get('category') or "").strip()
    valid_ids = [c['id'] for c in CATEGORIES]
    if category_id not in valid_ids and category_id != "":
        return jsonify({"error": f"Catégorie invalide"}),400
    
    frequency = int(data.get('frequency', 300))
    can_freq, msg_freq = can_use_frequency(user, frequency)
    if not can_freq:
        return jsonify({"error": msg_freq, "upgrade_required": True}),403
    
    notify_telegram = bool(data.get('notify_telegram', False))
    if notify_telegram:
        can_tg, msg_tg = can_use_telegram(user)
        if not can_tg:
            return jsonify({"error": msg_tg, "upgrade_required": True}),403
    
    alert_id = f"alert_{uuid.uuid4().hex[:10]}"
    keywords = data['keywords'].strip()
    description = (data.get('description') or "").strip()
    price_min = data.get('price_min')
    price_max = data.get('price_max')
    try: price_min = int(price_min) if price_min not in [None,'',0,'0'] else None
    except: price_min=None
    try: price_max = int(price_max) if price_max not in [None,'',0,'0'] else None
    except: price_max=None
    
    cur = db.cursor()
    cur.execute("""INSERT INTO alerts (id, user_id, keywords, category_id, description, price_min, price_max, location_mode, departments, regions, city, radius, frequency, active, notify_email, notify_telegram, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (alert_id, user['id'], keywords, category_id, description, price_min, price_max,
         data.get('location_mode','france'),
         json.dumps(data.get('departments')) if data.get('departments') else None,
         json.dumps(data.get('regions')) if data.get('regions') else None,
         data.get('city'), data.get('radius'),
         frequency, int(bool(data.get('active',True))), int(bool(data.get('notify_email',True))), int(notify_telegram),
         datetime.now().isoformat(), datetime.now().isoformat()))
    db.commit()
    cur.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
    return jsonify({"ok": True, "alert": dict(cur.fetchone())})

@app.route('/api/alerts/<alert_id>', methods=['GET','PUT','DELETE'])
@login_required
def manage_alert_route(alert_id):
    user = get_current_user()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM alerts WHERE id=? AND user_id=?", (alert_id, user['id']))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Alerte non trouvée"}),404
    if request.method=='GET':
        return jsonify({"alert": dict(row)})
    if request.method=='DELETE':
        cur.execute("DELETE FROM alerts WHERE id=? AND user_id=?", (alert_id, user['id']))
        cur.execute("DELETE FROM seen_ads WHERE alert_id=?", (alert_id,))
        db.commit()
        return jsonify({"ok": True})
    # PUT
    data = request.get_json() or {}
    fields = {}
    if 'keywords' in data: fields['keywords']=data['keywords'].strip()
    if 'category_id' in data or 'category' in data:
        cat = str(data.get('category_id') or data.get('category') or "").strip()
        valid_ids=[c['id'] for c in CATEGORIES]
        if cat!="" and cat not in valid_ids:
            return jsonify({"error":"Catégorie invalide"}),400
        fields['category_id']=cat
    if 'description' in data: fields['description']=data['description']
    if 'price_min' in data:
        try: fields['price_min']=int(data['price_min']) if data['price_min'] not in [None,'',0,'0'] else None
        except: fields['price_min']=None
    if 'price_max' in data:
        try: fields['price_max']=int(data['price_max']) if data['price_max'] not in [None,'',0,'0'] else None
        except: fields['price_max']=None
    if 'location_mode' in data: fields['location_mode']=data['location_mode']
    if 'departments' in data: fields['departments']=json.dumps(data['departments']) if data['departments'] else None
    if 'regions' in data: fields['regions']=json.dumps(data['regions']) if data['regions'] else None
    if 'frequency' in data:
        try:
            f=int(data['frequency'])
            can_freq, msg = can_use_frequency(user, f)
            if not can_freq:
                return jsonify({"error": msg, "upgrade_required": True}),403
            fields['frequency']=f
        except: pass
    if 'active' in data: fields['active']=int(bool(data['active']))
    if 'notify_email' in data: fields['notify_email']=int(bool(data['notify_email']))
    if 'notify_telegram' in data:
        if bool(data['notify_telegram']):
            can_tg, msg=can_use_telegram(user)
            if not can_tg:
                return jsonify({"error": msg, "upgrade_required": True}),403
        fields['notify_telegram']=int(bool(data['notify_telegram']))
    
    if not fields:
        return jsonify({"error":"Rien à modifier"}),400
    fields['updated_at']=datetime.now().isoformat()
    set_clause=", ".join([f"{k}=?" for k in fields])
    values=list(fields.values())+[alert_id, user['id']]
    cur.execute(f"UPDATE alerts SET {set_clause} WHERE id=? AND user_id=?", values)
    db.commit()
    cur.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
    return jsonify({"ok": True, "alert": dict(cur.fetchone())})

@app.route('/api/alerts/<alert_id>/toggle', methods=['POST'])
@login_required
def toggle_alert_route(alert_id):
    user = get_current_user()
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT active FROM alerts WHERE id=? AND user_id=?", (alert_id, user['id']))
    row=cur.fetchone()
    if not row: return jsonify({"error":"not found"}),404
    new_active=0 if row['active'] else 1
    cur.execute("UPDATE alerts SET active=?, updated_at=? WHERE id=? AND user_id=?", (new_active, datetime.now().isoformat(), alert_id, user['id']))
    db.commit()
    cur.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
    return jsonify({"ok": True, "alert": dict(cur.fetchone())})

@app.route('/api/alerts/<alert_id>/reset', methods=['POST'])
@login_required
def reset_alert_route(alert_id):
    user=get_current_user()
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM alerts WHERE id=? AND user_id=?", (alert_id, user['id']))
    if not cur.fetchone(): return jsonify({"error":"not found"}),404
    cur.execute("UPDATE alerts SET new_count=0, total_found=0 WHERE id=?", (alert_id,))
    cur.execute("DELETE FROM seen_ads WHERE alert_id=?", (alert_id,))
    db.commit()
    return jsonify({"ok": True})

@app.route('/api/alerts/<alert_id>/ads', methods=['GET'])
@login_required
def get_alert_ads(alert_id):
    user=get_current_user()
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM alerts WHERE id=? AND user_id=?", (alert_id, user['id']))
    if not cur.fetchone(): return jsonify({"error":"not found"}),404
    cur.execute("SELECT * FROM seen_ads WHERE alert_id=? AND user_id=? ORDER BY found_at DESC LIMIT 100", (alert_id, user['id']))
    ads=[]
    for r in cur.fetchall():
        try:
            ad=json.loads(r['ad_data'])
            ad['_found_at']=r['found_at']
            ads.append(ad)
        except: pass
    return jsonify({"ads": ads})

# --- Search ---
@app.route('/api/search', methods=['GET','POST'])
def api_search():
    if request.method=='GET':
        keywords=request.args.get('q','')
        category_id=request.args.get('category_id', request.args.get('category',''))
        filters={"price_min": request.args.get('price_min'), "price_max": request.args.get('price_max')}
    else:
        data=request.get_json() or {}
        keywords=data.get('keywords','')
        category_id=data.get('category_id') or data.get('category') or ""
        filters=data.get('filters',{})
    if not keywords:
        return jsonify({"ads":[], "total":0})
    result=search_leboncoin(keywords, category_id, filters)
    return jsonify(result)

# --- Admin ---
@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_users():
    db=get_db()
    cur=db.cursor()
    cur.execute("""
        SELECT u.*, 
        (SELECT COUNT(*) FROM alerts WHERE user_id=u.id) as alerts_count,
        (SELECT COUNT(*) FROM alerts WHERE user_id=u.id AND active=1) as active_alerts,
        (SELECT COUNT(*) FROM seen_ads WHERE user_id=u.id) as seen_count
        FROM users u ORDER BY u.created_at DESC
    """)
    users=[dict(r) for r in cur.fetchall()]
    # Ne pas exposer password_hash
    for u in users:
        u.pop('password_hash', None)
    return jsonify({"users": users})

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT COUNT(*) as c FROM users")
    total_users=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM users WHERE is_premium=1")
    premium_users=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM alerts")
    total_alerts=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM alerts WHERE active=1")
    active_alerts=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM seen_ads")
    total_seen=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM payments WHERE status='completed'")
    total_payments=cur.fetchone()['c']
    cur.execute("SELECT SUM(amount)/100.0 as total FROM payments WHERE status='completed'")
    row=cur.fetchone()
    revenue=row['total'] or 0
    return jsonify({
        "total_users": total_users,
        "premium_users": premium_users,
        "free_users": total_users - premium_users,
        "total_alerts": total_alerts,
        "active_alerts": active_alerts,
        "total_seen": total_seen,
        "total_payments": total_payments,
        "revenue": revenue,
        "checker": checker_status
    })

@app.route('/api/admin/users/<int:user_id>/make-premium', methods=['POST'])
@admin_required
def admin_make_premium(user_id):
    data=request.get_json() or {}
    months=int(data.get('months',1))
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
    if not cur.fetchone():
        return jsonify({"error":"User not found"}),404
    until=(datetime.now()+timedelta(days=30*months)).isoformat()
    cur.execute("UPDATE users SET is_premium=1, premium_until=? WHERE id=?", (until, user_id))
    db.commit()
    return jsonify({"ok": True, "premium_until": until})

@app.route('/api/admin/users/<int:user_id>/make-admin', methods=['POST'])
@admin_required
def admin_make_admin(user_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row=cur.fetchone()
    if not row: return jsonify({"error":"not found"}),404
    new_val=0 if row['is_admin'] else 1
    cur.execute("UPDATE users SET is_admin=? WHERE id=?", (new_val, user_id))
    db.commit()
    return jsonify({"ok": True, "is_admin": bool(new_val)})

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    if user_id==session['user_id']:
        return jsonify({"error":"Cannot delete yourself"}),400
    db=get_db()
    cur=db.cursor()
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    cur.execute("DELETE FROM alerts WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM seen_ads WHERE user_id=?", (user_id,))
    db.commit()
    return jsonify({"ok": True})

# --- Health & Status ---
@app.route('/health')
def health():
    return jsonify({"status":"ok","checker":checker_status,"stripe":bool(STRIPE_SECRET_KEY),"telegram":bool(TELEGRAM_BOT_TOKEN),"plans":PLANS})

@app.route('/api/status')
@login_required
def status():
    user=get_current_user()
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT COUNT(*) as c FROM alerts WHERE user_id=?", (user['id'],))
    alerts_count=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM alerts WHERE user_id=? AND active=1", (user['id'],))
    active_count=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM seen_ads WHERE user_id=?", (user['id'],))
    total_seen=cur.fetchone()['c']
    plan=get_user_plan(user)
    can_create, msg = can_create_alert(user, db)
    return jsonify({
        "checker": checker_status,
        "alerts_count": alerts_count,
        "active_count": active_count,
        "total_seen": total_seen,
        "plan": plan,
        "is_premium": is_premium_user(user),
        "is_admin": bool(user.get('is_admin')),
        "can_create": can_create,
        "limit_msg": msg,
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
        "user_telegram_configured": bool(user['telegram_chat_id'])
    })

# --- Frontend ---
@app.route('/')
def serve_front():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/admin')
def serve_admin():
    # Sert le même index, le JS détectera is_admin et affichera panel admin
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    fp=os.path.join(app.static_folder, path)
    if os.path.exists(fp):
        return send_from_directory(app.static_folder, path)
    if '.' not in path.split('/')[-1]:
        return send_from_directory(app.static_folder, 'index.html')
    return send_from_directory(app.static_folder, path)

init_db()

@app.before_request
def before_req():
    ensure_checker()
    g.user=get_current_user()

def ensure_checker():
    global checker_thread
    if checker_thread is None or not checker_thread.is_alive():
        checker_thread=threading.Thread(target=background_checker, daemon=True)
        checker_thread.start()

if __name__=='__main__':
    port=int(os.environ.get('PORT',5000))
    print(f"""
╔══════════════════════════════════════════════════════╗
║  🚀 LeBonAlert Platform v5 - Premium + Admin         ║
║  Port: {port}                                         ║
║  DB: {DB_PATH}                                       ║
║  Plans: Free 3 alertes / Premium 4.99€ illimité      ║
║  Stripe: {'✅' if STRIPE_SECRET_KEY else '❌ Démo (admin make-premium)'}                             ║
║  Telegram: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}                                    ║
╚══════════════════════════════════════════════════════╝
Admin par défaut: admin / admin123
    """)
    app.run(host='0.0.0.0', port=port, debug=False)
