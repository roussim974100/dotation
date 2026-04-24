#!/bin/bash
# Script de debug pour tracer le problème de mdp après deploy.sh
# Utilisation: ./debug-mdp.sh

OUTPUT_DIR="debug-output"
OUTPUT_FILE="$OUTPUT_DIR/debug-mdp-$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$OUTPUT_DIR"

{
  echo "=========================================="
  echo "DEBUG MDPConfiguration"
  echo "=========================================="
  echo "Date: $(date)"
  echo "User: $(whoami)"
  echo "Dir: $(pwd)"
  echo ""

  echo "=========================================="
  echo "[1] Hash du mdp AVANT changement"
  echo "=========================================="
  grep -A2 'username.*root' backend/users.json 2>/dev/null | head -10 || echo "users.json non trouvé"
  echo ""

  echo "=========================================="
  echo "[2] Backups AVANT changement"
  echo "=========================================="
  ls -lah backend/users.json.backup.* 2>/dev/null || echo "Aucun backup"
  echo ""

  echo "⏳ Attends que tu changes ton mdp via l'interface..."
  echo "Appuie sur ENTER quand c'est fait"
  read -p "➜ "
  echo ""

  echo "=========================================="
  echo "[3] Hash du mdp APRÈS changement (avant deploy)"
  echo "=========================================="
  grep -A2 'username.*root' backend/users.json 2>/dev/null | head -10
  echo ""

  echo "=========================================="
  echo "[4] Lancement du deploy.sh..."
  echo "=========================================="
  ./deploy.sh 2>&1
  DEPLOY_EXIT=$?
  echo "Exit code: $DEPLOY_EXIT"
  echo ""

  echo "=========================================="
  echo "[5] Hash du mdp APRÈS deploy"
  echo "=========================================="
  grep -A2 'username.*root' backend/users.json 2>/dev/null | head -10
  echo ""

  echo "=========================================="
  echo "[6] Backups APRÈS deploy"
  echo "=========================================="
  ls -lah backend/users.json.backup.* 2>/dev/null || echo "Aucun backup"
  echo ""

  echo "=========================================="
  echo "[7] Contenu complet du dernier backup .pre-reset"
  echo "=========================================="
  LATEST_PRESET=$(ls -t backend/users.json.backup.*.pre-reset 2>/dev/null | head -1)
  if [ -n "$LATEST_PRESET" ]; then
    echo "Fichier: $LATEST_PRESET"
    head -50 "$LATEST_PRESET"
  else
    echo "Aucun backup .pre-reset trouvé"
  fi
  echo ""

  echo "=========================================="
  echo "[8] Résumé des différences"
  echo "=========================================="
  echo "Ancien mdp (hash doit avoir changé): changé ?"
  echo "Backup .pre-reset créé: $(ls backend/users.json.backup.*.pre-reset 2>/dev/null | wc -l) fichiers"
  echo "Service status: $(systemctl is-active dotation 2>/dev/null || echo 'inconnu')"
  echo ""

  echo "=========================================="
  echo "Fichier de debug créé!"
  echo "=========================================="

} | tee "$OUTPUT_FILE"

echo ""
echo "✓ Résultats enregistrés dans: $OUTPUT_FILE"
echo ""
echo "Pour envoyer le fichier:"
echo "  cat $OUTPUT_FILE"
