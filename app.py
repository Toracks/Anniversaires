import os
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Ouvre une nouvelle connexion à la base Neon.

    On ouvre une connexion à chaque requête plutôt que d'en garder une seule
    ouverte en permanence : c'est plus simple à gérer et plus robuste pour
    un petit projet comme celui-ci (pas besoin de pool de connexions).
    """
    conn = psycopg2.connect(DATABASE_URL)
    return conn



@app.route("/")
def index():
    return send_from_directory(app.template_folder, "index.html")



@app.route("/api/anniversaires", methods=["GET"])
def liste_anniversaires():
    conn = get_db_connection()

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


    for r in resultats:
        if r["heure"] is not None:
            r["heure"] = r["heure"].strftime("%H:%M")

    return jsonify(resultats)


@app.route("/api/anniversaires/recherche", methods=["GET"])
def recherche_anniversaires():
    terme = request.args.get("q", "").strip()
    if not terme:
        return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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



@app.route("/api/anniversaires", methods=["POST"])
def ajouter_anniversaire():
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



@app.route("/api/anniversaires/<int:anniversaire_id>", methods=["PUT"])
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



@app.route("/api/anniversaires/<int:anniversaire_id>", methods=["DELETE"])
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



if __name__ == "__main__":
    app.run(debug=True, port=5000)