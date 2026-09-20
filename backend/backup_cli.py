"""Sauvegarde planifiee en ligne de commande, a lancer par cron / systemd / tache planifiee Windows.

  python backup_cli.py tick     decide seul s'il est temps de sauvegarder (a lancer toutes les 15 min)
  python backup_cli.py run      lance une sauvegarde immediate vers les destinations actives
  python backup_cli.py status   affiche l'etat de sante et l'historique recent

Codes de sortie : 0 = rien a faire ou succes, 1 = echec, 2 = configuration incomplete.
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backup_schedule as schedule  # noqa: E402
import backup_targets as targets  # noqa: E402


def _print_summary(summary):
    print(f"{'OK' if summary['ok'] else 'ECHEC'} : {summary['sent']} envoi(s), {summary['failed']} échec(s), {len(summary['deleted'])} archive(s) purgée(s)")
    for error in summary["errors"]:
        print(f"  - {error}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["tick", "run", "status"])
    parser.add_argument("--dest", action="append", help="identifiant de destination (repetable) ; defaut : toutes les actives")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # consoles Windows en cp1252
        except (AttributeError, ValueError):
            pass
    config = targets.load_config()

    if args.command == "status":
        state = schedule.health(config)
        print(f"[{state['level']}] {state['message']}")
        for entry in targets.read_history(10):
            print(f"  {entry['ts']} {'ok' if entry.get('ok') else 'ECHEC'} {entry.get('destination', '')} {entry.get('filename') or entry.get('error') or ''}")
        return 0

    if args.command == "tick" and not schedule.is_due(config, datetime.now()):
        return 0
    try:
        summary = schedule.run_scheduled(trigger="scheduled" if args.command == "tick" else "manual", dest_ids=args.dest)
    except schedule.ScheduleError as exc:
        print(exc.message, file=sys.stderr)
        return 0 if exc.code == "already_running" else 1
    _print_summary(summary)
    if summary["ok"]:
        return 0
    return 2 if any("introuvable" in e or "Aucune destination" in e for e in summary["errors"]) else 1


if __name__ == "__main__":
    sys.exit(main())
