"""Doublons de fiches "personne" (table persons) : plusieurs fiches representant en realite la meme personne,
le plus souvent creees quand un dossier n'a pas repris le personId d'un dossier precedent (voir
sync_person_and_dossier, models/dossier.py).

scan_person_duplicates : lecture seule, regroupe les fiches par identite normalisee (nom+prenom+service).
merge_persons : fusionne deux fiches EXPLICITEMENT choisies par un administrateur - jamais automatique (voir le
constat du 22/11/2026 : deviner par identite au moment de la creation risquerait de fusionner deux homonymes
reellement differents, protege par tests/test_person_grouping.py). La fusion ici n'est execute qu'un choix deja
fait par un humain, sur des fiches que le scan a lui-meme reconnues comme ayant la meme identite.

Aucun dossier n'est supprime ni modifie dans son contenu : seul le rattachement (person_id) de chaque dossier
est repointe vers la fiche conservee, dans la colonne ET dans payload_json (meta.personId), pour qu'un futur
enregistrement du dossier ne reparte pas sur l'ancienne fiche."""
import json
import unicodedata


def _normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def _identity(row):
    return (_normalize(row["nom"]), _normalize(row["prenom"]), _normalize(row["service"]))


def scan_person_duplicates(connection):
    """Groupes de 2+ fiches "personne" actives partageant la meme identite normalisee (nom+prenom+service)."""
    rows = connection.execute(
        """
        SELECT p.id, p.nom, p.prenom, p.service, p.qualite, p.created_at,
               (SELECT COUNT(*) FROM onboarding_dossiers d WHERE d.person_id = p.id) AS dossiers
        FROM persons p
        WHERE p.is_active = 1
        ORDER BY p.created_at
        """
    ).fetchall()
    groups = {}
    for row in rows:
        groups.setdefault(_identity(row), []).append(dict(row))
    return [
        {
            "nom": members[0]["nom"],
            "prenom": members[0]["prenom"],
            "service": members[0]["service"],
            "persons": members,
        }
        for members in groups.values()
        if len(members) > 1
    ]


def merge_persons(connection, keep_id, drop_id):
    """Fusionne drop_id dans keep_id. Leve ValueError si la fusion n'est pas sure (fiches introuvables, identiques,
    ou identite differente) : ce n'est pas a cette fonction de deviner, seulement d'executer un choix deja fait."""
    if keep_id == drop_id:
        raise ValueError("same_person")
    keep = connection.execute("SELECT * FROM persons WHERE id = ?", (keep_id,)).fetchone()
    drop = connection.execute("SELECT * FROM persons WHERE id = ?", (drop_id,)).fetchone()
    if not keep or not drop:
        raise ValueError("person_not_found")
    if _identity(keep) != _identity(drop):
        raise ValueError("identity_mismatch")

    connection.execute("UPDATE onboarding_dossiers SET person_id = ? WHERE person_id = ?", (keep_id, drop_id))

    moved_forms = 0
    for row in connection.execute("SELECT id, payload_json FROM dotation_forms WHERE person_id = ?", (drop_id,)).fetchall():
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        payload.setdefault("meta", {})["personId"] = keep_id
        connection.execute(
            "UPDATE dotation_forms SET person_id = ?, payload_json = ? WHERE id = ?",
            (keep_id, json.dumps(payload, ensure_ascii=False), row["id"]),
        )
        moved_forms += 1

    connection.execute("DELETE FROM persons WHERE id = ?", (drop_id,))
    return {"movedDossiers": moved_forms}
