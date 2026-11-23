from models.workflow import summarize_resource_item_details


def test_ressource_catalogue_sans_valeur_n_expose_aucune_donnee_technique():
    details = {
        "id": "resource_85f7", "code": "souris", "label": "Souris", "category": "materiel",
        "issuerService": "DSI", "requiresReturn": True, "displayOrder": 70,
        "fieldSchema": [{"id": "fld_1", "key": "marque", "label": "Marque"}], "fields": {},
    }
    assert summarize_resource_item_details(details) == ""


def test_ressource_catalogue_reprend_les_valeurs_saisies():
    details = {
        "fieldSchema": [{"id": "fld_1", "key": "marque", "label": "Marque", "type": "text"}],
        "fields": {"marque": "Dell"},
    }
    assert summarize_resource_item_details(details) == "Marque : Dell"


def test_item_statique_ignore_booleens_et_structures():
    assert summarize_resource_item_details({"marque": "HP", "flag": True, "liste": [1]}) == "HP"
