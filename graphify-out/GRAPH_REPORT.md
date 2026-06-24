# Graph Report - .  (2026-05-29)

## Corpus Check
- 153 files · ~128,773 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1082 nodes · 1769 edges · 58 communities detected
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 27 edges (avg confidence: 0.74)
- Token cost: 30,400 input · 10,400 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Dashboard Storage & Filters|Dashboard Storage & Filters]]
- [[_COMMUNITY_Form Logic & Resources|Form Logic & Resources]]
- [[_COMMUNITY_Bugfix Docs v3.18.1|Bugfix Docs v3.18.1]]
- [[_COMMUNITY_Admin UI (usersservicesresources)|Admin UI (users/services/resources)]]
- [[_COMMUNITY_Forms Persistence & Exports|Forms Persistence & Exports]]
- [[_COMMUNITY_Admin API Endpoints|Admin API Endpoints]]
- [[_COMMUNITY_Pages & HTML Routing|Pages & HTML Routing]]
- [[_COMMUNITY_Branding & Client Context|Branding & Client Context]]
- [[_COMMUNITY_UI Dialogs & Helpers|UI Dialogs & Helpers]]
- [[_COMMUNITY_Authentication & Permissions|Authentication & Permissions]]
- [[_COMMUNITY_Deployment & User Guide|Deployment & User Guide]]
- [[_COMMUNITY_Restitution Phase 2 UI|Restitution Phase 2 UI]]
- [[_COMMUNITY_Backend Utilities|Backend Utilities]]
- [[_COMMUNITY_Branding Admin UI|Branding Admin UI]]
- [[_COMMUNITY_Global Search (Ctrl+K)|Global Search (Ctrl+K)]]
- [[_COMMUNITY_Resource Catalog Migrations|Resource Catalog Migrations]]
- [[_COMMUNITY_App Bootstrap|App Bootstrap]]
- [[_COMMUNITY_Workflow Business Logic|Workflow Business Logic]]
- [[_COMMUNITY_Resource Ordering UI|Resource Ordering UI]]
- [[_COMMUNITY_Setup Wizard|Setup Wizard]]
- [[_COMMUNITY_Executive Dashboard|Executive Dashboard]]
- [[_COMMUNITY_Signature Link Management|Signature Link Management]]
- [[_COMMUNITY_App Settings & Theming|App Settings & Theming]]
- [[_COMMUNITY_Permissions Tests|Permissions Tests]]
- [[_COMMUNITY_Signature API Routes|Signature API Routes]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]

## God Nodes (most connected - your core abstractions)
1. `byId()` - 28 edges
2. `populateForm()` - 19 edges
3. `renderDraftList()` - 19 edges
4. `adminRequest()` - 16 edges
5. `README A Quai v3.18.3-prod` - 16 edges
6. `A Quai Guide de Deploiement v3.17.1` - 15 edges
7. `saveDraft()` - 14 edges
8. `saveBrandingSettings()` - 13 edges
9. `buildDashboardRow()` - 13 edges
10. `AppError` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Metaphore du voyage professionnel` --semantically_similar_to--> `Vision A Quai - voyage professionnel`  [INFERRED] [semantically similar]
  DEPLOYMENT_GUIDE.md → README.md
- `Scenario 4bis - signature a distance` --semantically_similar_to--> `Signature a distance via lien`  [INFERRED] [semantically similar]
  RECETTE_FONCTIONNELLE.md → GUIDE_UTILISATEUR.md
- `Scenario 4 - restitution` --semantically_similar_to--> `Restitution - workflow utilisateur`  [INFERRED] [semantically similar]
  RECETTE_FONCTIONNELLE.md → GUIDE_UTILISATEUR.md
- `Roles Admin et Lecture` --semantically_similar_to--> `Groupe lecture - permissions et restrictions`  [INFERRED] [semantically similar]
  wikijs.md → GUIDE_UTILISATEUR.md
- `Points d'attention (APP_SECRET_KEY, version/versions)` --semantically_similar_to--> `Recommandations avant remise (APP_SECRET_KEY, gunicorn, fpdf2)`  [INFERRED] [semantically similar]
  wikijs.md → LIVRAISON.md

## Hyperedges (group relationships)
- **Automatisation installation v3.18.0 - scripts + plans test + doc** — setup_install_debian_sh, setup_install_windows_ps1, test_plan_debian_doc, test_plan_windows_doc, installation_improvements_doc, setup_readme_doc [EXTRACTED 0.90]
- **Chaine bugfix 3.18.1 - extract_items + summarize_progress + PDF + test** — bugfixes_3181_bug1_checkboxes, bugfixes_3181_bug2_progression, bugfixes_3181_bug3_pdf, bugfixes_3181_extract_items, bugfixes_3181_summarize_progress, bugfixes_3181_test_unitaire [EXTRACTED 0.95]
- **Cleanup parcs mutualises 4 phases + fix quick_draft** — cleanup_pools_phase1_css_js, cleanup_pools_phase2_endpoint, cleanup_pools_phase3_permission, cleanup_pools_phase4_is_pool_resource, cleanup_pools_quick_draft_fix [EXTRACTED 0.95]

## Communities

### Community 0 - "Dashboard Storage & Filters"
Cohesion: 0.04
Nodes (107): acknowledgeDashboardUpdates(), applyDashboardFilters(), bindDashboardUpdateNotice(), bindDraftActionMenus(), bindSelectionActions(), bindSignatureLinkNotice(), buildAssignmentInfoEmailContent(), buildAssignmentSignatureEmailContent() (+99 more)

### Community 1 - "Form Logic & Resources"
Cohesion: 0.04
Nodes (82): addProgressIndicator(), applyLockState(), applySignatureProtection(), bindDynamicResourceToggles(), buildDynamicFieldInput(), buildDynamicResourceTrackingFields(), buildEquipmentSelectionMap(), buildIntangibleSelectionMap() (+74 more)

### Community 2 - "Bugfix Docs v3.18.1"
Cohesion: 0.03
Nodes (72): Bug #1 - cases decochees non sauvegardees, Bug #2 - dossiers finalises degrades au redemarrage, Bug #3 - items decoches dans PDF, Documentation technique fixes v3.18.1, Fonction extract_items() dans workflow.py, Test tests/test_extract_items_fix.py, Historique des versions A Quai, Politique de versionnement SemVer (+64 more)

### Community 3 - "Admin UI (users/services/resources)"
Cohesion: 0.11
Nodes (48): adminRequest(), appendResourceFieldRow(), approveUser(), bindResourceFieldRows(), byId(), closeUserEditModal(), collectResourceFieldSchema(), createResourceFieldRow() (+40 more)

### Community 4 - "Forms Persistence & Exports"
Cohesion: 0.06
Nodes (34): Exception, _apply_retraits_to_source(), build_excel_workbook(), download_response(), export_form_pdf(), export_forms(), export_forms_pdf_batch(), export_restitution_forms_pdf_batch() (+26 more)

### Community 5 - "Admin API Endpoints"
Cohesion: 0.05
Nodes (9): catalog_field_suggestions(), dashboard_stats(), _days_since(), db_diagnose(), db_import(), _diagnose_db_file(), _format_month_label(), _get_period_label() (+1 more)

### Community 6 - "Pages & HTML Routing"
Cohesion: 0.05
Nodes (4): build_login_forensic_details(), emergency_login(), login(), Route d'urgence temporaire pour debugger les problèmes CSRF.     À SUPPRIMER un

### Community 7 - "Branding & Client Context"
Cohesion: 0.11
Nodes (29): applyBrandingContent(), applyBrandingTheme(), bindHomeBrandLinks(), bootBranding(), bootClientContext(), bootCookieConsent(), buildClientDeviceLabel(), clearClientContextCookie() (+21 more)

### Community 8 - "UI Dialogs & Helpers"
Cohesion: 0.09
Nodes (21): askConfirm(), askWorkflowDialog(), ensureWorkflowDialog(), getCsrfToken(), _getToastStack(), initMojibakeRepair(), initUserMenu(), isDarkModeActive() (+13 more)

### Community 9 - "Authentication & Permissions"
Cohesion: 0.07
Nodes (22): build_user_context(), can_export_signature_assets(), check_user(), create_user(), current_user(), delete_user(), extract_first_forwarded_ip(), get_request_client_ip() (+14 more)

### Community 10 - "Deployment & User Guide"
Cohesion: 0.07
Nodes (32): Gestion des dependances Python en production, Historique - ajout fpdf2 (2026-03-31), Rationale - venv isole du Python systeme, Venv dedie /opt/dotation/backend/venv, Groupes et permissions par defaut, Pages admin (admin.html, comptes, services, ressources), Corbeille admin et restauration, Creer un dossier - workflow utilisateur (+24 more)

### Community 11 - "Restitution Phase 2 UI"
Cohesion: 0.12
Nodes (17): applyRestitutionReadOnlyMode(), applyRestitutionSignatureProtection(), bindRestitutionSignatureProtectionHandlers(), displayRestitutionSignatureModal(), getDraftById(), hideRestitutionLoader(), initRestitutionPage(), initSignaturePad() (+9 more)

### Community 12 - "Backend Utilities"
Cohesion: 0.11
Nodes (10): build_title(), dossier_type_label(), format_export_datetime(), get_restitution_signature_datetime(), get_signature_datetime(), mask_payload(), mask_text(), normalize_dossier_type() (+2 more)

### Community 13 - "Branding Admin UI"
Cohesion: 0.22
Nodes (19): brandingById(), brandingJson(), buildBrandingSaveSteps(), checkBeneficiaryTypesConflict(), closeBrandingSaveDialog(), collectBrandingPayload(), describeBrandingChanges(), describeValueChange() (+11 more)

### Community 14 - "Global Search (Ctrl+K)"
Cohesion: 0.19
Nodes (21): buildModal(), buildTriggerButton(), closeModal(), escapeHtml(), getActiveFilters(), getCurrentView(), init(), isOpen() (+13 more)

### Community 15 - "Resource Catalog Migrations"
Cohesion: 0.1
Nodes (16): migrate_builtin_display_order(), migrate_builtin_issuer_service(), migrate_builtin_resource_flags(), migrate_builtin_resource_schemas(), migrate_cartes_visite_quantite(), migrate_missing_builtin_resources(), migrate_suggest_flags(), migrate_telephone_imei_field() (+8 more)

### Community 16 - "App Bootstrap"
Cohesion: 0.15
Nodes (13): _AutoSecureSessionInterface, init_users_db(), migrate_missing_groups(), migrate_users_from_json(), Crée les groupes par défaut. Crée les groupes manquants, met à jour les existant, Crée l'utilisateur admin/admin par défaut s'il n'existe pas., Ajoute les groupes manquants même si la base de données existe déjà., Cookie Secure = True si la requête arrive en HTTPS, False sinon.     Fonctionne (+5 more)

### Community 17 - "Workflow Business Logic"
Cohesion: 0.25
Nodes (15): collect_resource_entries(), collect_resource_validation_errors(), compute_effective_workflow_status(), derive_dossier_status(), derive_restitution_workflow_status(), describe_assignment_condition(), extract_items(), is_dynamic_resource_complete() (+7 more)

### Community 18 - "Resource Ordering UI"
Cohesion: 0.24
Nodes (12): adminRequest(), bindDragAndDrop(), buildServiceGroups(), buildUpdatePayload(), byId(), getVisibleServiceGroups(), loadResources(), renderResources() (+4 more)

### Community 19 - "Setup Wizard"
Cohesion: 0.3
Nodes (15): $(), bindEvents(), getCsrfToken(), hideAlert(), init(), parseBeneficiaryTypes(), prefillFromApi(), renderBeneficiaryPreview() (+7 more)

### Community 20 - "Executive Dashboard"
Cohesion: 0.24
Nodes (15): bindFilterListeners(), init(), loadServiceOptions(), loadStats(), renderAlertes(), renderCharts(), renderKpis(), renderResourcesChart() (+7 more)

### Community 21 - "Signature Link Management"
Cohesion: 0.25
Nodes (13): create_signature_link(), generate_signature_token(), get_latest_signature_link(), get_signature_link_by_id(), get_signature_link_by_token(), materialize_signature_link(), revoke_signature_link(), revoke_signature_links_for_form() (+5 more)

### Community 22 - "App Settings & Theming"
Cohesion: 0.23
Nodes (8): build_public_settings_payload(), get_app_settings(), get_brand_logo_candidates(), get_dpo_email(), load_brand_logo_image(), _parse_beneficiary_types(), resolve_dark_mode(), resolve_theme_id()

### Community 23 - "Permissions Tests"
Cohesion: 0.14
Nodes (13): Test du système de validation des permissions au démarrage. Vérifie que validat, Vérifie que les routes principales sont couvertes., Vérifie que toutes les permissions requises sont définies dans les groupes., Vérifie que le groupe redaction ne peut pas voir tous les dossiers., Vérifie que le groupe lecture a des permissions limitées., Teste la fonction has_permission_in_group., Teste la fonction get_group_permissions., test_all_required_permissions_exist() (+5 more)

### Community 24 - "Signature API Routes"
Cohesion: 0.18
Nodes (3): _check_signature_verification(), view_form_restitution_signature(), view_form_signature()

### Community 25 - "Community 25"
Cohesion: 0.28
Nodes (10): buildAttributionTimingPreview(), buildDotationPreview(), buildMissingProgressPreview(), buildRestitutionTimingPreview(), buildTimingPreview(), getHoverCard(), hideStatusPreview(), positionHoverCard() (+2 more)

### Community 26 - "Community 26"
Cohesion: 0.29
Nodes (10): applyLoginMessages(), applyLoginTexts(), buildClientDeviceLabel(), detectBrowserName(), detectPlatformName(), fetchCsrfToken(), getAppText(), hydrateLoginClientContext() (+2 more)

### Community 27 - "Community 27"
Cohesion: 0.27
Nodes (9): failRestitutionSignatureBoot(), formatPublicRestitutionDateTime(), getRestitutionTokenFromUrl(), populatePublicRestitutionForm(), renderPublicRestitutionItems(), requestRestitutionSignatureJson(), showRestitutionSignatureError(), showRestitutionSuccess() (+1 more)

### Community 28 - "Community 28"
Cohesion: 0.17
Nodes (11): Tests critiques pour verifier les fixes appliques aux problemes identifies dans, TEST CYCLIQUE: read-modify-save-read      Workflow:     1. Charger un dossier, Verifier que updateCurrentPayload() synchronise correctement le payload     qua, CRITICAL FIX #1: Verifier que window.currentPayload est cree au chargement., CRITICAL FIX #4: Verifier que form.dataset.workflowStatus est synced post-save., CRITICAL FIX #2: Verifier que buildEquipmentSelectionMap lit le DOM, pas window., test_critical_fix_1_window_current_payload(), test_critical_fix_2_equipment_selection_map() (+3 more)

### Community 29 - "Community 29"
Cohesion: 0.31
Nodes (3): _AQuaiDoc, build_pdf_bytes(), FPDF

### Community 30 - "Community 30"
Cohesion: 0.35
Nodes (7): deleteTrashItem(), emptyTrash(), getFilteredTrash(), loadTrash(), renderTrash(), restoreTrashItem(), trashRequest()

### Community 31 - "Community 31"
Cohesion: 0.4
Nodes (8): _buildActions(), _buildProgressSection(), _buildResourceSection(), _buildUncSection(), closeQuickPanel(), getQuickPanel(), getQuickPanelOverlay(), openQuickPanel()

### Community 32 - "Community 32"
Cohesion: 0.33
Nodes (8): formatPublicDateTime(), getTokenFromUrl(), populatePublicForm(), renderResourceList(), requestPublicJson(), showPublicError(), showSignatureSuccess(), submitPublicSignature()

### Community 33 - "Community 33"
Cohesion: 0.24
Nodes (9): Tests pour valider le comportement du seed des groupes et de l'admin., Scénario 3 : Changement manuel de permissions     - retirer une permission d'un, Retourner l'heure actuelle au format ISO., Scénario 1 : Base vide     - seed_default_groups() doit créer tous les groupes, Scénario 2 : Base existante (avec utilisateur samir, pas admin)     - appeler i, test_scenario_1_empty_database(), test_scenario_2_existing_database_no_admin(), test_scenario_3_manual_permission_change() (+1 more)

### Community 34 - "Community 34"
Cohesion: 0.33
Nodes (5): build_request_client_log_details(), insert_app_log(), merge_app_log_details(), read_client_context_cookie(), read_login_attempt_context()

### Community 35 - "Community 35"
Cohesion: 0.31
Nodes (5): escapeHtml(), formatLogTarget(), loadLogs(), logsRequest(), renderPagination()

### Community 36 - "Community 36"
Cohesion: 0.31
Nodes (8): backup_file(), load_json(), merge_users_config(), Charge un fichier JSON., Sauvegarde un fichier JSON., Crée une sauvegarde du fichier avec timestamp., Fusionne les configurations utilisateurs., save_json()

### Community 37 - "Community 37"
Cohesion: 0.5
Nodes (6): applyPhase1ValidatedState(), buildPhase1Patch(), getEl(), initPhase1Page(), requestJson(), updateDateOrderWarning()

### Community 38 - "Community 38"
Cohesion: 0.33
Nodes (2): ensure_column(), table_columns()

### Community 39 - "Community 39"
Cohesion: 0.29
Nodes (6): get_group_permissions(), has_permission_in_group(), Valide que tous les groupes ont les permissions requises par les routes.     Af, Retourne les permissions d'un groupe, Vérifie qu'un groupe a une permission spécifique, validate_permissions_at_startup()

### Community 40 - "Community 40"
Cohesion: 0.29
Nodes (0): 

### Community 41 - "Community 41"
Cohesion: 0.47
Nodes (3): fetchAdminJson(), loadUncStats(), setMetric()

### Community 42 - "Community 42"
Cohesion: 0.5
Nodes (2): check_verification(), _verification_still_valid()

### Community 43 - "Community 43"
Cohesion: 0.7
Nodes (3): escapeHtml(), renderDiagnoseReport(), showDbResult()

### Community 44 - "Community 44"
Cohesion: 0.4
Nodes (0): 

### Community 45 - "Community 45"
Cohesion: 0.4
Nodes (0): 

### Community 46 - "Community 46"
Cohesion: 0.7
Nodes (5): A Quai Brand Identity, A Quai Email Icon (App Icon), A Quai Email Logo (Email Signature Logo), A Quai Email Logo Tight (Hero Brand Logo), A Quai Email Mark (Brand Mark)

### Community 47 - "Community 47"
Cohesion: 0.5
Nodes (2): build_retraits_pdf_bytes(), Génère un PDF de fiche de retraits pour un dossier mise_a_jour.

### Community 48 - "Community 48"
Cohesion: 0.83
Nodes (3): appendHelpSections(), appendHelpSummary(), initHelpPage()

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (2): migrate_forms_to_dossiers(), sync_person_and_dossier()

### Community 50 - "Community 50"
Cohesion: 0.67
Nodes (0): 

### Community 51 - "Community 51"
Cohesion: 0.67
Nodes (2): Test que les items décochés (selected=False) sont bien sauvegardés., test_extract_items_preserves_deselected()

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): pytest==9.0.2

## Knowledge Gaps
- **100 isolated node(s):** `Cookie Secure = True si la requête arrive en HTTPS, False sinon.     Fonctionne`, `Valide le token CSRF sur toutes les mutations JSON des endpoints /api/     pour`, `Crée les groupes par défaut. Crée les groupes manquants, met à jour les existant`, `Crée l'utilisateur admin/admin par défaut s'il n'existe pas.`, `Ajoute les groupes manquants même si la base de données existe déjà.` (+95 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 52`** (2 nodes): `config.py`, `get_app_secret_key()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `pytest==9.0.2`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `README A Quai v3.18.3-prod` connect `Bugfix Docs v3.18.1` to `Deployment & User Guide`?**
  _High betweenness centrality (0.005) - this node is a cross-community bridge._
- **Why does `A Quai Guide de Deploiement v3.17.1` connect `Bugfix Docs v3.18.1` to `Deployment & User Guide`?**
  _High betweenness centrality (0.004) - this node is a cross-community bridge._
- **Why does `AppError` connect `Forms Persistence & Exports` to `Backend Utilities`?**
  _High betweenness centrality (0.003) - this node is a cross-community bridge._
- **What connects `Cookie Secure = True si la requête arrive en HTTPS, False sinon.     Fonctionne`, `Valide le token CSRF sur toutes les mutations JSON des endpoints /api/     pour`, `Crée les groupes par défaut. Crée les groupes manquants, met à jour les existant` to the rest of the system?**
  _100 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Dashboard Storage & Filters` be split into smaller, more focused modules?**
  _Cohesion score 0.04 - nodes in this community are weakly interconnected._
- **Should `Form Logic & Resources` be split into smaller, more focused modules?**
  _Cohesion score 0.04 - nodes in this community are weakly interconnected._
- **Should `Bugfix Docs v3.18.1` be split into smaller, more focused modules?**
  _Cohesion score 0.03 - nodes in this community are weakly interconnected._