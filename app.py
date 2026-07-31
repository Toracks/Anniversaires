import os
import json
import tempfile
from functools import wraps
from datetime import timedelta, date
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template
from werkzeug.security import check_password_hash
from pywebpush import webpush, WebPushException
from dotenv import load_dotenv

# Charge les variables du fichier .env (utile en local ; sur Render, les
# variables d'environnement seront configurées directement dans le dashboard)
load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")

# Nécessaire à Flask pour signer/chiffrer le cookie de session
app.secret_key = os.environ.get("SECRET_KEY")
# Durée avant expiration de la session : 8 heures
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

DATABASE_URL = os.environ.get("DATABASE_URL")
APP_PASSWORD_HASH = os.environ.get("APP_PASSWORD_HASH")

# ---------------------------------------------------------------------------
# Configuration des notifications push (VAPID)
# ---------------------------------------------------------------------------
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY")
VAPID_CONTACT_EMAIL = os.environ.get("EMAIL_DESTINATAIRE", "contact@example.com")
CRON_SECRET = os.environ.get("CRON_SECRET")

# pywebpush a besoin d'un chemin de fichier vers la clé privée, pas du texte
# directement : on écrit donc le contenu de la variable d'environnement dans
# un fichier temporaire au démarrage de l'application.
_vapid_private_key_path = None
_vapid_pem_content = os.environ.get("VAPID_PRIVATE_KEY_PEM")
if _vapid_pem_content:
    _fichier_temp = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    _fichier_temp.write(_vapid_pem_content)
    _fichier_temp.close()
    _vapid_private_key_path = _fichier_temp.name


# ---------------------------------------------------------------------------
# Deux décorateurs de protection :
# - login_required_page : pour les pages HTML -> redirige vers /login
# - login_required_api : pour les routes API -> renvoie une erreur JSON 401
#   (une redirection casserait le fetch() côté JavaScript)
# ---------------------------------------------------------------------------
def login_required_page(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("connecte"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def login_required_api(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("connecte"):
            return jsonify({"erreur": "Non authentifié."}), 401
        return f(*args, **kwargs)
    return wrapper


def get_db_connection():
    """Ouvre une nouvelle connexion à la base Neon.

    On ouvre une connexion à chaque requête plutôt que d'en garder une seule
    ouverte en permanence : c'est plus simple à gérer et plus robuste pour
    un petit projet comme celui-ci (pas besoin de pool de connexions).
    """
    conn = psycopg2.connect(DATABASE_URL)
    return conn


# ---------------------------------------------------------------------------
# Page d'accueil : sert le calendrier (protégée par mot de passe)
# ---------------------------------------------------------------------------
@app.route("/")
@login_required_page
def index():
    return send_from_directory(app.template_folder, "index.html")


# ---------------------------------------------------------------------------
# Sert le service worker depuis la racine (/sw.js) plutôt que /static/sw.js :
# un service worker ne peut contrôler que les pages situées dans son propre
# dossier (ou en dessous) par défaut. En le servant depuis la racine, il
# couvre tout le site, y compris la page d'accueil "/".
# ---------------------------------------------------------------------------
@app.route("/sw.js")
def service_worker():
    return send_from_directory(app.static_folder, "sw.js")


# ---------------------------------------------------------------------------
# Connexion / déconnexion
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    erreur = None
    if request.method == "POST":
        mot_de_passe = request.form.get("mot_de_passe", "")
        if APP_PASSWORD_HASH and check_password_hash(APP_PASSWORD_HASH, mot_de_passe):
            session.clear()
            session["connecte"] = True
            session.permanent = True
            return redirect(url_for("index"))
        erreur = "Mot de passe incorrect."
    return render_template("login.html", erreur=erreur)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# GET /api/anniversaires
# Renvoie la liste de tous les anniversaires enregistrés.
# ---------------------------------------------------------------------------
@app.route("/api/anniversaires", methods=["GET"])
@login_required_api
def liste_anniversaires():
    conn = get_db_connection()
    # RealDictCursor renvoie chaque ligne sous forme de dictionnaire
    # (ex: {"id": 1, "prenom": "Jean", ...}) plutôt qu'un simple tuple.
    # C'est beaucoup plus pratique à convertir en JSON pour le frontend.
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, prenom, nom, jour, mois, annee, heure
        FROM anniversaires
        ORDER BY mois, jour
        """
    )
    resultats = cur.fetchall()
    cur.close()
    conn.close()

    # psycopg2 renvoie les colonnes TIME sous forme d'objet time Python,
    # qu'on convertit en texte ("14:30") pour que ce soit du JSON valide.
    for r in resultats:
        if r["heure"] is not None:
            r["heure"] = r["heure"].strftime("%H:%M")

    return jsonify(resultats)


# ---------------------------------------------------------------------------
# GET /api/anniversaires/recherche?q=jean
# Recherche des anniversaires par prénom (insensible à la casse).
# ---------------------------------------------------------------------------
@app.route("/api/anniversaires/recherche", methods=["GET"])
@login_required_api
def recherche_anniversaires():
    terme = request.args.get("q", "").strip()
    if not terme:
        return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # ILIKE = comparaison texte insensible à la casse en Postgres.
    # Le % avant/après le terme permet de matcher une partie du prénom.
    cur.execute(
        """
        SELECT id, prenom, nom, jour, mois, annee, heure
        FROM anniversaires
        WHERE prenom ILIKE %s
        ORDER BY mois, jour
        """,
        (f"%{terme}%",),
    )
    resultats = cur.fetchall()
    cur.close()
    conn.close()

    for r in resultats:
        if r["heure"] is not None:
            r["heure"] = r["heure"].strftime("%H:%M")

    return jsonify(resultats)


# ---------------------------------------------------------------------------
# POST /api/anniversaires
# Ajoute un nouvel anniversaire.
# Corps JSON attendu : { prenom, nom, jour, mois, annee, heure }
# ---------------------------------------------------------------------------
@app.route("/api/anniversaires", methods=["POST"])
@login_required_api
def ajouter_anniversaire():
    data = request.get_json(silent=True) or {}

    prenom = (data.get("prenom") or "").strip()
    jour = data.get("jour")
    mois = data.get("mois")

    # Validation des champs obligatoires : prénom, jour et mois.
    # On renvoie une erreur 400 claire si quelque chose manque,
    # plutôt que de laisser la base de données planter silencieusement.
    if not prenom:
        return jsonify({"erreur": "Le prénom est obligatoire."}), 400
    if not jour or not mois:
        return jsonify({"erreur": "La date (jour et mois) est obligatoire."}), 400

    try:
        jour = int(jour)
        mois = int(mois)
    except (TypeError, ValueError):
        return jsonify({"erreur": "Jour et mois doivent être des nombres."}), 400

    if not (1 <= mois <= 12) or not (1 <= jour <= 31):
        return jsonify({"erreur": "Date invalide."}), 400

    nom = (data.get("nom") or "").strip() or None
    annee = data.get("annee") or None
    heure = (data.get("heure") or "").strip() or None

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        INSERT INTO anniversaires (prenom, nom, jour, mois, annee, heure)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, prenom, nom, jour, mois, annee, heure
        """,
        (prenom, nom, jour, mois, annee, heure),
    )
    nouvel_anniversaire = cur.fetchone()
    conn.commit()

    # Si la date ajoutée tombe aujourd'hui, on notifie tout de suite plutôt
    # que d'attendre la vérification quotidienne du lendemain
    notifier_si_aujourdhui(nouvel_anniversaire["id"], prenom, nom, jour, mois, cur, conn)

    cur.close()
    conn.close()

    if nouvel_anniversaire["heure"] is not None:
        nouvel_anniversaire["heure"] = nouvel_anniversaire["heure"].strftime("%H:%M")

    return jsonify(nouvel_anniversaire), 201


# ---------------------------------------------------------------------------
# PUT /api/anniversaires/<id>
# Modifie un anniversaire existant.
# ---------------------------------------------------------------------------
@app.route("/api/anniversaires/<int:anniversaire_id>", methods=["PUT"])
@login_required_api
def modifier_anniversaire(anniversaire_id):
    data = request.get_json(silent=True) or {}

    prenom = (data.get("prenom") or "").strip()
    jour = data.get("jour")
    mois = data.get("mois")

    if not prenom:
        return jsonify({"erreur": "Le prénom est obligatoire."}), 400
    if not jour or not mois:
        return jsonify({"erreur": "La date (jour et mois) est obligatoire."}), 400

    try:
        jour = int(jour)
        mois = int(mois)
    except (TypeError, ValueError):
        return jsonify({"erreur": "Jour et mois doivent être des nombres."}), 400

    nom = (data.get("nom") or "").strip() or None
    annee = data.get("annee") or None
    heure = (data.get("heure") or "").strip() or None

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        UPDATE anniversaires
        SET prenom = %s, nom = %s, jour = %s, mois = %s, annee = %s, heure = %s,
            derniere_annee_notifiee = NULL
        WHERE id = %s
        RETURNING id, prenom, nom, jour, mois, annee, heure
        """,
        (prenom, nom, jour, mois, annee, heure, anniversaire_id),
    )
    resultat = cur.fetchone()
    conn.commit()

    if resultat is None:
        cur.close()
        conn.close()
        return jsonify({"erreur": "Anniversaire introuvable."}), 404

    # Si la nouvelle date tombe aujourd'hui, on notifie tout de suite
    notifier_si_aujourdhui(anniversaire_id, prenom, nom, jour, mois, cur, conn)

    cur.close()
    conn.close()

    if resultat["heure"] is not None:
        resultat["heure"] = resultat["heure"].strftime("%H:%M")

    return jsonify(resultat)


# ---------------------------------------------------------------------------
# DELETE /api/anniversaires/<id>
# Supprime un anniversaire.
# ---------------------------------------------------------------------------
@app.route("/api/anniversaires/<int:anniversaire_id>", methods=["DELETE"])
@login_required_api
def supprimer_anniversaire(anniversaire_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM anniversaires WHERE id = %s", (anniversaire_id,))
    lignes_supprimees = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if lignes_supprimees == 0:
        return jsonify({"erreur": "Anniversaire introuvable."}), 404

    return jsonify({"succes": True})


# ---------------------------------------------------------------------------
# Lancement en local (sur Render, c'est gunicorn qui démarre l'appli,
# donc ce bloc ne sert que quand tu testes sur ta propre machine).
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Envoie une notification push à tous les appareils abonnés pour un
# anniversaire donné. Réutilisée à la fois par la vérification quotidienne
# (cron) et par l'ajout/modification en direct (si la date tombe aujourd'hui).
# Renvoie le nombre d'appareils notifiés avec succès.
# ---------------------------------------------------------------------------
def envoyer_notification_push(prenom, nom, cur, conn):
    nom_complet = prenom
    if nom:
        nom_complet += f" {nom}"

    titre = f"🎂 Aujourd'hui c'est l'anniversaire de {prenom} !"
    corps = f"{nom_complet} fête son anniversaire aujourd'hui. Clique pour plus de détails."
    payload = json.dumps({"titre": titre, "corps": corps})

    cur.execute("SELECT id, endpoint, p256dh, auth FROM push_subscriptions")
    abonnements = cur.fetchall()

    nb_notifies = 0
    for abonnement in abonnements:
        subscription_info = {
            "endpoint": abonnement["endpoint"],
            "keys": {"p256dh": abonnement["p256dh"], "auth": abonnement["auth"]},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=_vapid_private_key_path,
                vapid_claims={"sub": f"mailto:{VAPID_CONTACT_EMAIL}"},
            )
            nb_notifies += 1
        except WebPushException as err:
            if err.response is not None and err.response.status_code == 410:
                cur.execute("DELETE FROM push_subscriptions WHERE id = %s", (abonnement["id"],))
                conn.commit()

    return nb_notifies


# ---------------------------------------------------------------------------
# Si un anniversaire tombe aujourd'hui et n'a pas encore été notifié cette
# année, envoie la notification tout de suite et marque l'année comme faite
# (utile quand on ajoute/modifie un anniversaire après l'heure du cron).
# ---------------------------------------------------------------------------
def notifier_si_aujourdhui(anniversaire_id, prenom, nom, jour, mois, cur, conn):
    aujourdhui = date.today()
    if jour != aujourdhui.day or mois != aujourdhui.month:
        return

    cur.execute("SELECT derniere_annee_notifiee FROM anniversaires WHERE id = %s", (anniversaire_id,))
    ligne = cur.fetchone()
    if ligne and ligne["derniere_annee_notifiee"] == aujourdhui.year:
        return  # déjà notifié aujourd'hui (par le cron ou un envoi précédent)

    envoyer_notification_push(prenom, nom, cur, conn)
    cur.execute(
        "UPDATE anniversaires SET derniere_annee_notifiee = %s WHERE id = %s",
        (aujourdhui.year, anniversaire_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# GET /api/vapid-public-key
# Fournit la clé publique VAPID au JavaScript, pour qu'il puisse s'abonner.
# ---------------------------------------------------------------------------
@app.route("/api/vapid-public-key", methods=["GET"])
@login_required_api
def vapid_public_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})


# ---------------------------------------------------------------------------
# POST /api/push-subscribe
# Enregistre un nouvel abonnement aux notifications (un par appareil/navigateur).
# ---------------------------------------------------------------------------
@app.route("/api/push-subscribe", methods=["POST"])
@login_required_api
def push_subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"erreur": "Abonnement invalide."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    # ON CONFLICT : si cet appareil est déjà abonné (même endpoint), on ne
    # duplique pas la ligne, on met juste à jour ses clés au cas où.
    cur.execute(
        """
        INSERT INTO push_subscriptions (endpoint, p256dh, auth)
        VALUES (%s, %s, %s)
        ON CONFLICT (endpoint) DO UPDATE SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth
        """,
        (endpoint, p256dh, auth),
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"succes": True}), 201


# ---------------------------------------------------------------------------
# GET /cron/verifier-anniversaires?secret=...
# Route appelée une fois par jour par cron-job.org : vérifie les anniversaires
# du jour et envoie une notification push à tous les appareils abonnés.
# Protégée par un secret (passé en paramètre d'URL) pour éviter que n'importe
# qui sur internet puisse la déclencher.
# ---------------------------------------------------------------------------
@app.route("/cron/verifier-anniversaires", methods=["GET"])
def verifier_anniversaires():
    secret_fourni = request.args.get("secret")
    if not CRON_SECRET or secret_fourni != CRON_SECRET:
        return jsonify({"erreur": "Non autorisé."}), 403

    aujourdhui = date.today()
    annee_courante = aujourdhui.year

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # On sélectionne les anniversaires du jour, pas encore notifiés cette année
    cur.execute(
        """
        SELECT id, prenom, nom, annee
        FROM anniversaires
        WHERE jour = %s AND mois = %s
          AND (derniere_annee_notifiee IS NULL OR derniere_annee_notifiee != %s)
        """,
        (aujourdhui.day, aujourdhui.month, annee_courante),
    )
    anniversaires_du_jour = cur.fetchall()

    if not anniversaires_du_jour:
        cur.close()
        conn.close()
        return jsonify({"message": "Aucun anniversaire aujourd'hui.", "notifies": 0})

    # Récupère tous les appareils abonnés aux notifications
    cur.execute("SELECT id, endpoint, p256dh, auth FROM push_subscriptions")
    abonnements = cur.fetchall()

    nb_notifies = 0
    for anniversaire in anniversaires_du_jour:
        nb_notifies += envoyer_notification_push(
            anniversaire["prenom"], anniversaire["nom"], cur, conn
        )

        # On marque cet anniversaire comme notifié pour cette année
        cur.execute(
            "UPDATE anniversaires SET derniere_annee_notifiee = %s WHERE id = %s",
            (annee_courante, anniversaire["id"]),
        )
        conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "message": f"{len(anniversaires_du_jour)} anniversaire(s) traité(s).",
        "notifies": nb_notifies,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)