import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.models.workflow import extract_items

def test_extract_items_preserves_deselected():
    """Test que les items décochés (selected=False) sont bien sauvegardés."""
    payload = {
        "materiel": {
            "badge": {
                "selected": True,
                "assignedAt": "2024-01-15"
            },
            "veste": {
                "selected": False,  # ← Item décoche
                "assignedAt": "2024-01-15"
            },
            "ordinateur": {
                "selected": True,
                "nomPoste": "PC-001"
            },
            "ecran": {
                "selected": False,  # ← Item décoche aussi
                "marque": "Dell"
            }
        },
        "immateriel": {
            "vpn": {
                "selected": False  # ← Item décoche
            },
            "email": {
                "selected": True
            }
        },
        "restitution": {}
    }

    items = extract_items(payload)

    # Convertir en dict pour faciliter les tests
    items_by_key = {item["item_key"]: item for item in items}

    # Vérifier que TOUS les items sont présents
    assert "badge" in items_by_key, "Badge doit être présent"
    assert "veste" in items_by_key, "Veste doit être présente (même si décochée)"
    assert "ordinateur" in items_by_key, "Ordinateur doit être présent"
    assert "ecran" in items_by_key, "Écran doit être présent (même si décoché)"
    assert "vpn" in items_by_key, "VPN doit être présent (même si décoché)"
    assert "email" in items_by_key, "Email doit être présent"

    # Vérifier que le champ 'assigned' reflète bien l'état 'selected'
    assert items_by_key["badge"]["assigned"] == True, "Badge sélectionné doit avoir assigned=True"
    assert items_by_key["veste"]["assigned"] == False, "Veste décochée doit avoir assigned=False"
    assert items_by_key["ordinateur"]["assigned"] == True, "Ordinateur sélectionné doit avoir assigned=True"
    assert items_by_key["ecran"]["assigned"] == False, "Écran décoché doit avoir assigned=False"
    assert items_by_key["vpn"]["assigned"] == False, "VPN décoché doit avoir assigned=False"
    assert items_by_key["email"]["assigned"] == True, "Email sélectionné doit avoir assigned=True"

    print("✅ Test réussi ! Les items décochés sont maintenant sauvegardés correctement.")
    print(f"   - Total items: {len(items)}")
    print(f"   - Items assignés (selected=True): {sum(1 for i in items if i['assigned'])}")
    print(f"   - Items non assignés (selected=False): {sum(1 for i in items if not i['assigned'])}")

if __name__ == "__main__":
    test_extract_items_preserves_deselected()
