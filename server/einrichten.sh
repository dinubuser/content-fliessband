#!/bin/bash
# Einmalig auf dem Server als root: Benutzer, Ordner und venv (nur pytest) für den Briefkasten.
# Wiederholbar, ändert nichts Bestehendes. Aufruf vom Mac:
#   ssh -i ~/.ssh/your_ssh_key root@your-server-ip 'bash -s' < server/einrichten.sh
set -euo pipefail
python3 -c 'import sys, sqlite3
if sys.version_info < (3, 10): sys.exit("Python " + sys.version.split()[0] + " zu alt, nötig ist 3.10 oder neuer")
if sqlite3.sqlite_version_info < (3, 24, 0): sys.exit("SQLite " + sqlite3.sqlite_version + " zu alt, nötig ist 3.24 oder neuer")
print("Python", sys.version.split()[0], "und SQLite", sqlite3.sqlite_version, "passen")'
id fliessband >/dev/null 2>&1 || useradd --system --user-group --home-dir /var/lib/fliessband --shell /usr/sbin/nologin fliessband
install -d -m 755 -o root -g root /opt/fliessband /opt/fliessband/app
install -d -m 750 -o fliessband -g fliessband /var/lib/fliessband
install -d -m 750 -o root -g fliessband /etc/fliessband
[ -x /opt/fliessband/venv/bin/python ] || python3 -m venv /opt/fliessband/venv
/opt/fliessband/venv/bin/pip install -q --disable-pip-version-check pytest
echo "Server vorbereitet: Benutzer fliessband, /opt/fliessband, /var/lib/fliessband, /etc/fliessband"
