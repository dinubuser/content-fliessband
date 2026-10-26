#!/bin/bash
# Kopiert server/ auf den Server, führt die Tests dort aus und startet NUR fliessband-briefkasten neu.
# Daten (/var/lib/fliessband) und geheim.env (/etc/fliessband) werden nie berührt.
set -euo pipefail
# Konfiguration aus .env im Projektordner (siehe .env.example)
[ -f "$(dirname "$0")/../.env" ] && { set -a; . "$(dirname "$0")/../.env"; set +a; }
SERVER="${FLIESSBAND_SERVER:-root@your-server-ip}"
SSH="ssh -i ${FLIESSBAND_SSH_KEY:-$HOME/.ssh/your_ssh_key} -o IdentitiesOnly=yes"
cd "$(dirname "$0")"

echo "1/3 Code kopieren nach /opt/fliessband/app"
rsync -a --delete -e "$SSH" --exclude '__pycache__' --exclude '.pytest_cache' \
  briefkasten tests system pytest.ini "$SERVER:/opt/fliessband/app/"
$SSH "$SERVER" 'chown -R root:root /opt/fliessband/app && chmod -R u=rwX,go=rX /opt/fliessband/app'

echo "2/3 Tests auf dem Server"
$SSH "$SERVER" 'cd /opt/fliessband/app && PYTHONDONTWRITEBYTECODE=1 /opt/fliessband/venv/bin/python -m pytest -q -p no:cacheprovider tests'

echo "3/3 Dienst fliessband-briefkasten neu starten (nur dieser Dienst)"
$SSH "$SERVER" '
  if ! cmp -s /opt/fliessband/app/system/fliessband-briefkasten.service /etc/systemd/system/fliessband-briefkasten.service; then
    install -m 644 /opt/fliessband/app/system/fliessband-briefkasten.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable fliessband-briefkasten.service >/dev/null 2>&1
  fi
  systemctl restart fliessband-briefkasten.service
  sleep 3
  systemctl is-active fliessband-briefkasten.service
'
echo "Fertig."
