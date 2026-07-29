import os
from functools import wraps
from datetime import timedelta
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template
from werkzeug.security import check_password_hash
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
    cur.close()
    conn.close()

    if resultat is None:
        return jsonify({"erreur": "Anniversaire introuvable."}), 404

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
if __name__ == "__main__":
    app.run(debug=True, port=5000)