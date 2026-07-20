# 🔔 LeBonAlert Platform - SaaS Multi-Utilisateurs

**Plateforme d'alertes Leboncoin.fr pour toutes les catégories** : voitures, immobilier, emploi, maison, loisirs... avec comptes utilisateurs, notifications **Email + Telegram**.

> L'évolution de ton projet : de l'alerte perso "Clio 1983" à un vrai site où chaque membre crée ses propres alertes.

---

## ✨ Fonctionnalités

### Pour chaque membre inscrit:
- **Compte personnel** : username + email + mot de passe (hashé)
- **Alertes illimitées** sur **toutes les catégories** Leboncoin:
  - 🚗 Véhicules (Voitures, Motos, Vélos, Utilitaires, Nautisme)
  - 🏠 Immobilier (Ventes, Locations, Coloc, Bureaux)
  - 💼 Emploi (Offres d'emploi)
  - 💻 Multimédia (Informatique, Image & Son, Téléphonie, Consoles)
  - 🛋️ Maison (Ameublement, Electroménager, Bricolage, Jardinage...)
  - ⚽ Loisirs (Livres, Animaux, Sports, Collection, Jeux...)
  - Et toutes les autres (40+ catégories)
- **Gestion complète CRUD** :
  - ➕ Créer : mots-clés + catégorie + prix min/max + localisation + fréquence
  - ✏️ Modifier : change tout en 1 clic
  - ⏸️ Pause / ▶️ Activer : désactive temporairement
  - 🗑️ Supprimer : avec confirmation
  - 🔄 Reset : remet à zéro compteur + historique vues
  - 📋 Filtrer par alerte ou par catégorie
- **Notifications par utilisateur** :
  - 📧 **Email** : beau template HTML avec photo, prix, lien
  - 📲 **Telegram** : photo + détails instantanés via bot plateforme
  - Chaque alerte peut activer email et/ou telegram séparément
  - Chaque utilisateur configure son `telegram_chat_id` et active/désactive
- **Surveillance background H24** : thread qui vérifie toutes les alertes actives de tous les users toutes les 30s-10min selon fréquence
- **Anti-spam** : premier run = pas de notif sur anciennes annonces, uniquement nouvelles

### Technique:
- Backend Flask + SQLite (users, alerts, seen_ads, checker_stats)
- Auth par session (30j), password hash Werkzeug
- API REST : `/api/auth/*`, `/api/alerts/*`, `/api/user/*`, `/api/categories`, `/api/search`
- Frontend SPA vanilla JS (pas de framework) - rapide
- Docker prêt pour Railway / Render / VPS
- Email : SMTP (Gmail, Sendgrid, etc.) ou mode démo log dans `data/emails_demo.log`
- Telegram : 1 bot global (TELEGRAM_BOT_TOKEN), chaque user fournit son chat_id

---

## 🚀 Lancer en local

```bash
cd leboncoin-platform
pip install -r requirements.txt
python app.py
# Ouvre http://localhost:5000
```

Crée un compte (ex: chasseur_clio / toi@email.com / mdp123456) → tu as déjà une alerte exemple "clio 1983" offerte.

---

## 🌐 Héberger en ligne (SaaS)

### Railway.app (recommandé 24/7)

```bash
# Push sur GitHub
git init && git add . && git commit -m "platform v4"
git remote add origin https://github.com/ton_user/lebonalert-platform.git
git push -u origin main

# Sur railway.app/new -> Deploy from GitHub
# Variables à ajouter:
SECRET_KEY=une_cle_aleatoire_tres_longue
TELEGRAM_BOT_TOKEN=123456:ABC (ton bot @BotFather)
SMTP_HOST=smtp.gmail.com
SMTP_USER=ton.email@gmail.com
SMTP_PASS=mot_de_passe_app_gmail
SMTP_FROM=alertes@tondomaine.fr
DATA_DIR=/tmp/data
```

Ajoute un **Volume** : `/tmp/data` pour persister la DB SQLite.

Start command : `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 app:app`

Tu obtiens `https://lebonalert-platform.up.railway.app` → ton site public où les gens s'inscrivent !

### Render.com (gratuit)

Même chose, utilise `render.yaml` fourni. Ajoute UptimeRobot pour éviter veille.

---

## 📲 Configurer Telegram pour tous les utilisateurs

1. Crée un bot avec @BotFather : `/newbot` → `LeBonAlertPlatformBot`
2. Copie le token → mets-le en env `TELEGRAM_BOT_TOKEN` sur Railway
3. Explique à tes membres comment trouver leur Chat ID :
   - Ils envoient un message à ton bot
   - Ils ouvrent `https://api.telegram.org/botTOKEN/getUpdates` → récupèrent `chat.id`
   - Ils collent ce ID dans Réglages → Telegram Chat ID → Sauver → Test Telegram
4. Dès qu'une annonce sort, ils reçoivent la photo + prix + lien instantané

---

## 📧 Configurer Email

### Gmail (le plus simple):
1. Active 2FA sur ton compte Google
2. Va sur https://myaccount.google.com/apppasswords → crée un mot de passe app
3. Mets en env:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=ton.email@gmail.com
   SMTP_PASS=le_mot_de_passe_app_16_caracteres
   SMTP_FROM=ton.email@gmail.com
   ```
4. Teste avec bouton "Test Email" dans les réglages

Sans SMTP configuré : mode démo, les emails sont loggés dans `data/emails_demo.log` et console.

---

## 🗂️ Structure DB

- `users` : id, username, email, password_hash, telegram_chat_id, telegram_enabled, email_enabled
- `alerts` : id, user_id, keywords, category_id, price_min/max, location_mode, frequency, active, notify_email/telegram, new_count, total_found
- `seen_ads` : alert_id, user_id, leboncoin_id, ad_data (JSON), found_at, notified_email/telegram
- `checker_stats` : historique vérifications

---

## 🔐 Sécurité

- Mots de passe hashés (Werkzeug PBKDF2)
- Sessions HTTP Only, SameSite Lax
- Chaque user ne voit que SES alertes (WHERE user_id = ? partout)
- Validation catégories vs liste officielle
- Rate limit captcha Leboncoin géré (pause 60s)

---

## 🎯 Roadmap

- [ ] Upload avatar
- [ ] PWA mobile
- [ ] Web Push Notifications navigateur
- [ ] Export CSV annonces
- [ ] Partage alerte publique (lien)
- [ ] Paiement Stripe pour alertes premium illimitées
- [ ] Admin panel liste users

---

## 💸 Business Model possible

- Gratuit : 3 alertes max, fréquence min 5 min, email seulement
- Premium 4.99€/mois : alertes illimitées, 30s, Telegram + Email, support catégories pro

Tu peux ajouter Stripe facilement : check `user.is_premium`.

---

Besoin d'aide pour déployer avec email + telegram ? Dis-moi ton SMTP et token bot, je te configure.
