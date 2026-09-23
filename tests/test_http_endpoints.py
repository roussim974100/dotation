"""Tests HTTP d'integration sur une base TEMPORAIRE (sous-processus + APP_DATA_DIR) : couvre les endpoints qui n'avaient
aucun test (logo, journaux, statistiques, exports, PDF par lots, stocks, parc...) et verifie qu'aucun endpoint prive
ne repond a un visiteur anonyme."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def http(tmp_path_factory):
    data = tmp_path_factory.mktemp("aquai_http")
    env = dict(os.environ, APP_UPDATE_CHECK="0", APP_DATA_DIR=str(data), APP_CUSTOM_BRANDING_DIR=str(data / "branding"), PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "tests" / "_http_scenarios.py")], cwd=str(ROOT), env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert result.returncode == 0, (result.stderr or result.stdout)[-1500:]
    line = next(line for line in result.stdout.splitlines() if line.startswith("JSON>>"))
    return json.loads(line[len("JSON>>"):])


def test_no_private_endpoint_answers_an_anonymous_visitor(http):
    assert http["anonymous_leaks"] == []


def test_admin_get_endpoints_never_crash(http):
    assert http["admin_get_errors"] == []
    assert http["admin_get_checked"] >= 30  # le parcours couvre bien tous les GET sans parametre


def test_logo_upload_validation(http):
    assert http["logo_valid"] in (200, 201)
    assert http["logo_bad_extension"] == 400
    assert http["logo_bad_magic"] == 400
    assert http["logo_too_large"] in (400, 413)
    assert http["logo_missing"] == 400


@pytest.mark.parametrize("name", [
    "trash", "logs", "unc_stats", "services_csv_template", "services_export_csv", "forms_export", "forms_export_unc",
    "catalog_quality", "stock", "units", "units_stats", "dashboard_stats", "backup_info", "groups", "session",
])
def test_admin_read_endpoints_answer_200(http, name):
    assert http[name] == 200


def test_catalog_quality_and_csv_shapes(http):
    assert http["catalog_quality_has_total"] is True
    assert http["services_csv_is_text"] is True


def test_pdf_endpoints_refuse_bad_input_without_crashing(http):
    assert 400 <= http["pdf_batch_empty"] < 500
    assert 400 <= http["restitution_pdf_batch_empty"] < 500
    assert http["restitution_pdf_unknown"] == 404
    assert http["pdf_unknown"] == 404


def test_stock_and_parc_actions_on_unknown_objects(http):
    assert http["stock_unknown_resource"] == [400, "not_quantity_resource"]
    assert http["unit_action_unknown"] in (400, 404)


def test_logo_url_with_file_scheme_is_never_stored(http):
    assert not http["logo_url_file_scheme_stored"]


def test_login_rate_limit_ignores_a_forged_forwarded_for_header(http):
    """10 tentatives passent, la 11e est refusee, alors que chacune annonce une IP differente dans X-Forwarded-For."""
    assert http["login_rate_limited_at_attempt"] == 11


def test_a_fresh_install_gives_the_admin_group_the_parc_manage_right(http):
    """Regression : sur une installation neuve, l'administrateur doit pouvoir gerer le parc et les stocks des le depart."""
    assert http["admin_has_parc_manage"] is True


def test_update_endpoints_report_status_and_refuse_the_web_update_by_default(http):
    status_code, keys = http["update_status"]
    assert status_code == 200 and {"current", "latest", "available", "can_update", "enabled", "progress"} <= set(keys)
    assert http["update_check_disabled"] == [200, False]  # verification desactivee : aucune requete reseau
    assert http["update_start_disabled"] == [403, "update_disabled"]


def test_partial_settings_update_keeps_existing_values(http):
    assert http["partial_put_keeps"] == ["Organisation Test", "aide@test.fr"]


def test_invalid_beneficiary_type_is_refused(http):
    assert http["bad_beneficiary_status"] == 400


def test_setup_cannot_be_replayed_without_confirmation(http):
    assert http["setup_first_run"] == 200 or http["setup_first_run"] == 409  # une base neuve peut deja etre configuree
    assert http["setup_rerun_locked"] == 409 and http["setup_rerun_org_name"] != "Pirate"
    assert http["setup_rerun_confirmed"] == 200


def test_org_wizard_preview_writes_nothing_and_applies_only_the_previewed_plan(http):
    assert http["wizard_preview_status"] == 200 and http["wizard_preview_writes_nothing"] is True
    assert http["wizard_preview_actions"] == [["create", "instrument_de_musique"], ["create", "stock_vetement"], ["deactivate", "zoneAlarme"]]
    assert http["wizard_apply_bad_hash"] == 409 and http["wizard_apply_unconfirmed"] == 400
    assert http["wizard_apply_status"] == 200
    assert http["wizard_created_codes"] == ["instrument_de_musique", "stock_vetement"]
    assert http["wizard_zone_alarme_active"] == 0
    assert http["wizard_settings_after"] == ["other", "member:Membre,staff:员工", "4"]


def test_org_wizard_is_idempotent_and_add_only(http):
    assert http["wizard_second_preview_creates"] == [] and http["wizard_second_preview_settings"] == []


def test_org_wizard_rejects_bad_input_and_anonymous(http):
    assert http["wizard_xss_label"] == 400 and http["wizard_bad_context"] == 400
    assert http["wizard_unknown_template"] == [200, ["blocked"]]
    assert all(code in (401, 403, 302) for code in http["wizard_anonymous"])


def test_startup_checklist_reflects_the_real_state(http):
    assert http["checklist"] == [7, ["backup", "domains", "dpo", "org_name", "resources", "support", "wizard"], True]
    assert http["checklist_wizard_done_after_apply"] is True
    assert http["checklist_anonymous"] in (401, 403, 302)


def test_pilotage_threshold_changes_the_danger_state_of_dossiers(http):
    """Un dossier incomplet qui demarre dans 5 jours : « Dans les temps » avec un seuil de 3 jours, « En danger » avec 7 ; retour au seuil 3 = retour a l'etat initial."""
    assert http["pilotage_seuil_3"][0] == "ok" and http["pilotage_seuil_3"][1] == "Dans les temps"
    assert http["pilotage_seuil_7"] == ["warning", "En danger"]
    assert http["pilotage_public_payload"] == 7  # la valeur est aussi publiee au navigateur (calcul cote client)
    assert http["pilotage_retour_seuil_3"] == http["pilotage_seuil_3"]


def test_pilotage_threshold_does_not_change_the_executive_summary(http):
    """La page Synthese a ses propres seuils (3 / 7 / 30 jours) : le reglage « Seuil d'alerte pilotage » ne la modifie pas."""
    assert http["synthese_inchangee_par_le_seuil"] is True


def test_legacy_field_names_are_shown_under_the_current_catalog_names(http):
    """Dossier saisi avec d'anciens noms de champs : le formulaire recoit aussi les valeurs sous les noms du catalogue (sinon il les affiche vides)."""
    assert http["legacy_fields_aligned"] == {"nom_du_poste": "PC-ANCIEN-1", "numero_de_serie": "SN-ANCIEN-1", "adresse_email": "ancien@exemple.fr", "marque": "HP"}
    # rien n'est retire : les anciens noms restent presents (aucune perte de donnees)
    assert http["legacy_fields_old_keys_kept"] == {"nomPoste": "PC-ANCIEN-1", "numeroSerie": "SN-ANCIEN-1", "adresse": "ancien@exemple.fr"}


def test_field_health_scan_and_repair_only_adds_current_names(http):
    """Diagnostic : les valeurs orphelines sont listees avec leur cible ; la reparation les rattache (ajout seulement) et un second passage ne trouve plus rien."""
    assert [tuple(x) for x in http["health_scan_before"]] == [("adresse", "adresse_email"), ("nomPoste", "nom_du_poste"), ("numeroSerie", "numero_de_serie")]
    assert http["health_repaired_fields"] == 3
    assert http["health_scan_after"] == []


def test_custom_resource_end_to_end_no_data_loss(http):
    """Ressource creee de toutes pieces (tous types de champs, libelles atypiques) : saisie, relecture, PUT(GET) idempotent, valeur orpheline conservee, renommage de cle, alias, masquage, PDF, export."""
    assert http["e2e_create_status"] in (200, 201)
    assert "n_de_serie" in http["e2e_keys"], http["e2e_keys"]  # « N° de série » -> un seul « _ », comme cote JS
    assert "numeroInventaire" in http["e2e_keys"]  # cle valide gardee telle quelle (pas de mise en minuscules)
    assert http["e2e_roundtrip_lossless"] is True
    assert http["e2e_put_get_idempotent"] is True
    assert http["e2e_orphan_kept_on_save"] is True


def test_custom_resource_rename_hide_and_exports(http):
    assert [a.lower() for a in http["e2e_alias_after_rename"]] == ["numeroinventaire"]  # alias compare sans casse (canonical_key)
    assert [a.lower() for a in http["e2e_alias_survives_next_save"]] == ["numeroinventaire"]  # l'editeur ne renvoie pas les alias : ils ne se perdent pas
    assert http["e2e_value_visible_after_rename"] is True
    assert http["e2e_hidden_field_still_in_schema"] is True
    assert http["e2e_hidden_value_kept"] is True
    assert http["e2e_pdf_status"] == 200
    assert http["e2e_export_contains_values"] is True


def test_optimistic_lock_refuses_a_stale_save_instead_of_overwriting(http):
    assert http["lock_first_save"] == 200
    assert http["lock_second_save"] == [409, "form_conflict"]
    assert http["lock_value_kept"] == "Premiere modification"  # la modification de l'autre personne n'a pas ete ecrasee
    assert http["lock_without_base_still_saves"] == 200  # anciens clients / imports : comportement inchange


def test_resource_used_by_dossiers_cannot_be_deleted(http):
    assert http["delete_used_resource"] == [409]
    assert http["delete_unused_resource"] == 200


def test_database_health_report(http):
    assert http["health_report"] == {"integrity": "ok", "brokenReferences": 0}
    assert http["health_report_has_schema_version"] == 4
    assert http["health_report_status_known"] is True


def test_db_export_then_import_keeps_data_and_schema(http):
    assert http["db_export_is_sqlite"] is True
    assert http["db_import_status"] == 200
    assert http["db_import_keeps_forms"] is True
    assert http["db_import_health"] == ["ok", 4]


def test_importing_an_older_database_upgrades_its_schema_immediately(http):
    assert http["old_db_import"] == [200, 4, True]


def test_configured_beneficiary_types_and_status_labels_are_served(http):
    assert http["vocab_custom_type_kept"] == [201, "stagiaire"]  # avant : ramene a « agent »
    assert http["vocab_public_status_labels"] == "En attente de signature"
    assert http["vocab_label_python"] == "Stagiaire"


def test_masked_profile_cannot_overwrite_a_dossier_with_masked_values(http):
    assert http["masked_can_read"] == 200
    assert http["masked_put_status"] == 403
    assert http["masked_put"] == {"error": "masked_scope_read_only"}
    assert http["masked_real_name_intact"] == "MASQUE"  # le vrai nom n'a pas ete remplace par une valeur masquee


def test_custom_type_with_mandate_flag_keeps_its_mandate_and_title(http):
    assert http["mandate_custom_type"] == ["Conseiller municipal", "CONSEILLER MUNICIPAL"]
    assert http["mandate_public_flag"] == {"agent": False, "elu": True, "stagiaire": False, "conseiller": True}


def test_config_export_import_is_additive_and_previewable(http):
    assert http["config_export"] == [200, "aquai-config", True, False]  # pas de donnee personnelle dans le fichier
    assert http["config_preview"] == [False, ["import_nouvelle"], False]  # l'apercu n'ecrit rien
    assert http["config_apply"] == [True, True, True]  # nouvelle ressource creee, ressource existante inchangee
    assert http["config_idempotent"] == [[], []]  # rejouer ne cree plus rien
    assert http["config_bad_file"] == 400


def test_init_db_is_idempotent(http):
    """Redemarrer l'application (init_db rejoue toutes les creations et migrations) ne change ni le schema, ni les donnees."""
    assert http["init_idempotent_schema"] is True
    assert http["init_idempotent_data"] == {}
    assert http["init_idempotent_migrations"] is True


def test_unexpected_errors_give_a_shareable_code_and_no_raw_message(http):
    status, prefix, length, request_id, header = http["obs_error_shape"]
    assert status == 500 and prefix == "E-" and length == 8
    assert request_id == "requete-de-test-01" == header  # identifiant du proxy conserve et renvoye
    assert http["obs_message_has_no_value"] is True  # jamais la valeur qui a provoque l'erreur
    assert http["obs_same_defect_same_code"] is True  # meme defaut = meme code (le support le retrouve)
    assert http["obs_bad_request_id_replaced"] is True  # pas d'injection dans le journal
    assert http["obs_log_has_code_not_value"] is True


def test_diagnostic_pack_contains_no_personal_data(http):
    """Base pleine de valeurs « sentinelles » (noms, e-mail, serie, libelles, options, chemin reseau, organisation) : aucune ne doit sortir."""
    assert http["diag_status"] == 200
    assert http["diag_leaks"] == []
    assert http["diag_content"][0] == "aquai-diagnostic" and http["diag_content"][2] is True and http["diag_content"][3] == 1
    status, names, checksum_ok, zip_leaks = http["diag_zip"]
    assert status == 200 and names == ["LISEZMOI.txt", "checksums.txt", "diagnostic.json"] and checksum_ok is True and zip_leaks == []


def test_diagnostic_guard_refuses_personal_looking_content_and_is_admin_only(http):
    assert http["diag_guard_misses"] == []  # e-mail, chemin reseau, IP, URL, chemin de fichier : tous refuses
    assert http["diag_forbidden_for_anonymous"] in (401, 403)


def test_stock_uses_explicit_field_roles_not_key_names(http):
    assert http["stock_roles_kept"] == [["qte_en_stock", "quantity", True, False], ["taille_pointure", "variant", False, True]]
    assert http["stock_libre_levels"] == [True, True, [["42", 5]]]  # 5 unites reservees en pointure 42, malgre des noms de cle libres


def test_retrait_via_mise_a_jour_resynchronise_le_parc_du_dossier_source(http):
    """3.60.1 : avant le correctif, un objet retire via un dossier « mise a jour » restait affiche comme detenu
    dans le parc (resource_units jamais resynchronise pour le dossier SOURCE). Verifie que l'objet redevient disponible."""
    assert http["retrait360_source_status_active"] == "active"
    assert http["retrait360_unit_status_before"] == ["assigned"]
    assert http["retrait360_unit_status_after"] == ["in_stock"]
    assert http["retrait360_source_items_returned"].get("poste_retrait360", {}).get("state") == "conforme"
