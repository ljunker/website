Website
============

https://kryptikk.de

```
curl kryptikk.de
```

Setup
-----

```
make venv
make check-deps
```

Usage
-----

```
$ make help
make build         default target, builds the site into ./_site
                   BASE_PATH=/preview/<slug> make build: Build mit Pfad-Praefix (Branch-Preview)
make venv          create ./.venv and install pinned requirements
make check-deps    check to ensure needed dependencies are installed
make check         check tools syntax using shellcheck
make serve         serve ./_site locally with sample calendar (see README)
make serve-termin  run the appointment-request service locally (console mail)
make test          run the unit tests of the appointment-request service
make deploy        deploy the site (using rsync)
make update-nginx  copy nginx config if changed
make update-termin install/restart the appointment-request service (systemd)
make all           clean, build and deploy the site
make clean         remove any generated files
```

Lokal testen (mit Beispielterminen)
-----------------------------------

```
make build serve      # http://localhost:8000
```

`make serve` startet `dev/dev-server.py` (nur Python-Standardbibliothek). Er
liefert `_site` aus und beantwortet `/schedule/calendar.ics` mit einem zur
Laufzeit erzeugten Beispiel-Feed (Termine relativ zu heute, fiktive Daten;
produktiv kommt der Feed per nginx von iCloud). Es wird nichts in `_site`
geschrieben. Varianten:

```
PORT=8080 make serve          # anderer Port
CALENDAR=empty make serve     # leerer Feed ("Keine Termine ...")
CALENDAR=error make serve     # HTTP 500 (Fehlerkarte mit Abo-Link)
```

Terminanfragen
--------------

Auf `/terminanfrage` kann man einen Calltermin anfragen. Der Dienst in
`termin/` (nur Python-Standardbibliothek, SQLite) speichert die Anfrage und
schickt eine Benachrichtigung per SMTP. Im passwortgeschützten Dashboard
`/termin-admin/` lassen sich Anfragen annehmen, ablehnen oder mit Freitext
beantworten; die Antwort geht per Mail an die anfragende Person. Es gibt keine
automatische Eingangsbestätigung. Statusregel: Annehmen setzt `angenommen`,
Ablehnen `abgelehnt`; eine Freitext-Antwort setzt `beantwortet`, aber nur bei
noch neuen Anfragen (ein vorhandener Status bleibt).

nginx leitet `/termin-api/` und `/termin-admin/` an `127.0.0.1:18090` weiter
(siehe `kryptikk.de`), der Dienst lauscht nur dort.

### Einrichtung auf dem Server

1. Benutzer für den Dienst anlegen (ohne Schreibrechte im Checkout):

   ```
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin kryptikk-termin
   ```

2. Passwort-Hash für das Dashboard erzeugen:

   ```
   python3 termin/hash-password
   ```

3. Env-Datei anlegen, Vorlage ist `termin/env.example` (echte Werte gehören
   nie ins Repo). Rechte 600:

   ```
   sudo install -m 600 -o root -g root termin/env.example /etc/kryptikk-termin.env
   sudo $EDITOR /etc/kryptikk-termin.env
   ```

   Dort `SMTP_*`, `MAIL_FROM`, `NOTIFY_TO`, `ADMIN_PASSWORD_HASH` (Ausgabe von
   `hash-password`) und `SECRET_KEY` setzen. Als `SMTP_PASSWORD` ein
   **App-Passwort** des Mail-Anbieters verwenden, nicht das Hauptpasswort.
   Port 587 mit `SMTP_SECURITY=starttls` oder 465 mit `ssl`.

4. Der Clone muss für den Dienstbenutzer lesbar sein (Ubuntu-Homes sind
   standardmäßig 0750, dann ggf. `chmod o+x ~` bzw. ein Clone außerhalb des
   Home). Prüfen mit:

   ```
   sudo -u kryptikk-termin test -r <ADMIN_CLONE>/termin/app.py && echo ok
   ```

   `make update-termin` bricht ab, wenn diese Prüfung fehlschlägt.

5. systemd-Unit installieren und starten (im Admin-Clone, nicht im Checkout
   des Deploy-Benutzers; die Unit startet den Code aus genau diesem Clone):

   ```
   make update-termin
   ```

6. nginx-Konfiguration einspielen: `make update-nginx`.

Danach nach Änderungen am Dienst im Admin-Clone `git pull --ff-only && make
update-termin`. Das interaktive `./upgrade` erledigt das mit; im
unbeaufsichtigten Lauf (ohne Terminal, ohne sudo) wird der Dienst
übersprungen und nur ein Hinweis ausgegeben; den Neustart erledigt dann der
Admin manuell im Admin-Clone.
Die Datenbank liegt unter `/var/lib/kryptikk-termin/`. Logs:
`journalctl -u kryptikk-termin`.

### Lokal testen

```
make build
make serve-termin     # Dienst auf 127.0.0.1:18090, Mails nur auf der Konsole
make serve            # in einem zweiten Terminal: http://localhost:8000/terminanfrage
```

`make serve-termin` nutzt `termin/dev.sqlite3`, kein Secure-Cookie und das
Dashboard-Passwort `dev` (Dashboard: http://localhost:8000/termin-admin/). Der
Dev-Server leitet `/termin-api/` und `/termin-admin/` an den Dienst weiter.
Eigene Werte lassen sich in `termin/.env` ablegen (steht in `.gitignore`).
Die Tests laufen mit `make test`.

Upgrade
-------

Pull the latest changes, rebuild and deploy in one step:

```
./upgrade
```

Automatisches Deployment
------------------------

Der Workflow `.github/workflows/deploy.yml` verbindet sich bei jedem Push auf
`main` (und manuell über `workflow_dispatch`) per SSH mit dem Server und führt
dort im Checkout `./upgrade` aus. Der Server holt den Stand selbst per
`git pull`, der Workflow macht keinen Checkout. Deployments laufen nie
parallel und werden nicht abgebrochen.

### Repository-Secrets

| Secret               | Inhalt |
|----------------------|--------|
| `DEPLOY_HOST`        | Hostname oder IP des Servers |
| `DEPLOY_USER`        | Benutzer auf dem Server (z. B. `deploy`) |
| `DEPLOY_PORT`        | SSH-Port, optional (Standard 22) |
| `DEPLOY_PATH`        | Absoluter Pfad des Checkouts auf dem Server |
| `DEPLOY_SSH_KEY`     | Privater Schlüssel (kompletter Inhalt der Datei) |
| `DEPLOY_KNOWN_HOSTS` | Hostkey des Servers, Ausgabe von `ssh-keyscan` |

Schlüsselpaar erzeugen (dediziert, ohne Passphrase):

```
ssh-keygen -t ed25519 -C github-deploy -f ./github-deploy
```

Der öffentliche Teil (`github-deploy.pub`) kommt in
`~/.ssh/authorized_keys` des Deploy-Benutzers, am besten eingeschränkt, z. B.:

```
restrict ssh-ed25519 AAAA... github-deploy
```

Der private Teil (`github-deploy`) wandert in das Secret `DEPLOY_SSH_KEY`;
danach die lokalen Dateien löschen. Den Hostkey zum Pinnen holt man mit:

```
ssh-keyscan -p <DEPLOY_PORT> <DEPLOY_HOST>
```

Host und Port müssen exakt den Werten der Secrets `DEPLOY_HOST` und
`DEPLOY_PORT` entsprechen, sonst schlägt die Hostkey-Prüfung fehl. Die Ausgabe
kommt unverändert in `DEPLOY_KNOWN_HOSTS`. Der Workflow nutzt
`StrictHostKeyChecking=yes` mit genau dieser Datei, es gibt kein
`ssh-keyscan` zur Laufzeit.

### Voraussetzungen auf dem Server

- Der Checkout muss sich ohne Rückfrage per `git pull --ff-only` von GitHub
  aktualisieren lassen (z. B. Deploy-Key oder HTTPS bei öffentlichem Repo).
- Ein dedizierter Deploy-Benutzer besitzt den Checkout und den Webroot
  `/var/www/kryptikk.de/html` (für nginx lesbar):

  ```
  sudo chown -R deploy: /var/www/kryptikk.de/html
  sudo chown -R deploy: <DEPLOY_PATH>
  ```

  Der bestehende Checkout muss ebenfalls dem Deploy-Benutzer gehören (alternativ
  frisch als Deploy-Benutzer klonen), sonst scheitern `git pull`
  (safe.directory) und Schreibzugriffe auf `.venv` und `_site`.
  `make deploy` führt `rsync` dann ohne sudo aus. **Für den Deploy-Benutzer
  ist keine sudoers-Regel nötig.**
- Der unbeaufsichtigte Lauf (ohne Terminal, z. B. SSH aus dem Workflow)
  überspringt `sudo -v` und `make update-nginx` und läuft ganz ohne sudo.
  Änderungen an der nginx-Konfiguration spielt ein Admin-Benutzer mit sudo
  manuell aus **seinem eigenen Clone** ein, den der Deploy-Benutzer nicht
  beschreiben kann (z. B. der bestehende Checkout des Admins), nie aus
  `<DEPLOY_PATH>`:
  `cd <ADMIN_CLONE> && git pull --ff-only && make update-nginx`.
  Der Grund: Der Deploy-Benutzer kontrolliert die Dateien in `<DEPLOY_PATH>`
  (Makefile, `kryptikk.de`); mit sudo ausgeführt, würde das dem Deploy-Benutzer
  root verschaffen. Vor dem Einspielen empfiehlt sich ein kurzer Blick auf
  `git log` bzw. `git diff` für `kryptikk.de`. Die Website selbst
  veröffentlicht normalerweise der Workflow (beim nächsten Push auf `main` oder
  manuell per `workflow_dispatch`); ein Deploy aus dem Admin-Clone ist nur
  die Ausnahme (siehe Hinweise).
- Der Fallback von `make deploy` auf `sudo rsync` (Webroot nicht
  beschreibbar) greift im klassischen Setup ohne separaten Deploy-Benutzer
  und im Admin-Clone im Setup mit Deploy-Benutzer, wenn der Ausführende des
  interaktiven `./upgrade` sudo hat, aber den Webroot nicht besitzt; der
  Deploy-Benutzer braucht ihn nicht. Der Fallback behält Besitzer und Gruppe
  des bestehenden Webroots bei (`rsync --chown` mit der zuvor ermittelten
  numerischen uid:gid, benötigt rsync ≥ 3.1) und setzt feste Modi
  (`--chmod=D755,F644`: Ordner 755, Dateien 644), damit die umask des Admins
  nicht übernommen wird und nginx alles lesen kann; fehlt der Webroot,
  bricht er mit einer Fehlermeldung ab. Gehört der Webroot bereits dem
  falschen Benutzer (z. B. nach einem früheren `sudo rsync` ohne `--chown`;
  erkennbar an „sudo: a terminal is required…“ im Workflow), repariert man
  das mit `sudo chown -R <deploy-user>: /var/www/kryptikk.de/html` und
  startet den Deploy-Workflow danach erneut.

Hinweise:

- Der Deploy-Schlüssel gibt die Rechte des Deploy-Benutzers: Er kann den
  Checkout verändern und die Website (den Webroot) überschreiben oder
  verunstalten, braucht dafür aber kein root. Der Deploy-Benutzer darf daher
  keine sudo-Rechte haben (kein sudoers-Eintrag, nicht in der Gruppe `sudo`
  bzw. `wheel`), sonst ist die Isolation hinfällig.
- Der Admin führt `make` oder `./upgrade` niemals mit sudo in `<DEPLOY_PATH>`
  (oder in einem anderen Verzeichnis, das der Deploy-Benutzer beschreiben
  kann) aus, sonst ist die Isolation ebenfalls hinfällig.
- Ein interaktives `make deploy` bzw. `./upgrade` im Admin-Clone ist
  möglich (der Fallback behält Besitzer und Gruppe des Webroots), veröffentlicht
  aber den `_site`-Stand des Admin-Clones, nicht den von `main`, bis der
  nächste Workflow-Deploy ihn wieder überschreibt. Der Clone sollte daher
  vorher auf dem gewünschten Stand sein (`git pull --ff-only`).
- Empfehlungen: dedizierter Deploy-Benutzer; der Schlüssel liegt nur als
  Repository-Secret und auf keiner anderen Maschine; `restrict` in
  `authorized_keys`; den Branch `main` per Branch Protection schützen und für
  den Deploy-Job optional ein GitHub-Environment mit Required Reviewers
  verwenden, denn jeder Push auf `main` wird als dieser Benutzer gebaut und
  veröffentlicht.

Branch-Previews
---------------

Jeder Push auf einen Branch `feature/<stichwort>` (nur `a-z`, `0-9`, `-`) wird
automatisch auf dem Server gebaut und unter
`https://kryptikk.de/preview/<stichwort>/` bereitgestellt, z. B.
`feature/dark-mode` unter `/preview/dark-mode/`. Mehrere Previews laufen
parallel; `/preview/` listet alle. Beim Löschen des Branches verschwindet die
Preview. Previews sind öffentlich erreichbar, aber `noindex`
(`X-Robots-Tag`, `robots.txt`). Der Workflow `.github/workflows/preview.yml`
ruft dafür auf dem Server `./preview deploy|remove <branch>` auf (gleiche
Secrets wie `deploy.yml`, aber eigene `concurrency`-Gruppe pro Branch, damit
wartende Produktions-Deploys nicht verdrängt werden; auf dem Server
serialisiert ein Lock nur die Previews untereinander, `./upgrade` läuft
unabhängig davon) und schreibt die URL
in die Job-Zusammenfassung.

`./preview` holt den Branch per `git fetch` nach `refs/previews/<slug>` (eigener
Namensraum, kollidiert nicht mit `./upgrade`; Haupt-Checkout bleibt unberührt),
legt einen Worktree unter `.previews/<slug>` an, baut mit
`make clean build BASE_PATH=/preview/<slug>` und synchronisiert nach
`$PREVIEW_ROOT/<slug>/` (Default `/var/www/kryptikk.de/previews`).

`BASE_PATH` (nur leer oder `^/preview/[a-z0-9-]+$`) setzt ein Präfix vor alle
root-relativen Links, Assets, CSS-`url()` und Pfade in den generierten JS-Dateien
(`make/rebase-site`). Ohne `BASE_PATH` ist der Build unverändert. Bewusst
root-relativ bleiben die Endpunkte, die es nur in Produktion gibt:
`/termin-api/`, `/termin-admin/`, `/schedule/calendar.ics`, `/schrittjagd-api/`,
`/log/`, `/ping`, `/ip`. Das Terminformular in einer Preview sendet daher an die
Produktions-API.

### Einmalige Einrichtung auf dem Server

```
sudo mkdir -p /var/www/kryptikk.de/previews
sudo chown <deploy-user> /var/www/kryptikk.de/previews
```

Die nginx-Änderung (`location ^~ /preview/` in `kryptikk.de`) einmalig per
interaktivem `./upgrade` bzw. `make update-nginx` im Admin-Clone einspielen
(der unbeaufsichtigte CI-Lauf überspringt nginx). `preview` und die Workflow-
Datei liegen erst nach dem Merge auf `main` auf dem Server bzw. im Default-
Branch; `delete`-Events lösen nur Workflows des Default-Branches aus. Der Build
braucht Netzwerk (Kalender, Sheets, Cover-Metadaten), wie `./upgrade`.

Lizenz / Herkunft
-----------------

Teile dieses Projekts basieren auf der ysap-Website von Dave Eddy
(https://github.com/bahamas10/ysap, MIT). Details, Dateiliste und Lizenztext
stehen in [NOTICE](NOTICE).
