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
make venv          create ./.venv and install pinned requirements
make check-deps    check to ensure needed dependencies are installed
make check         check tools syntax using shellcheck
make serve         serve site locally out of ./_site
make deploy        deploy the site (using rsync)
make update-nginx  copy nginx config if changed
make all           clean, build and deploy the site
make clean         remove any generated files
```

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
  veröffentlicht der Workflow (beim nächsten Push auf `main` oder manuell per
  `workflow_dispatch`), nicht der Admin-Clone.
- Der Fallback von `make deploy` auf `sudo rsync` (Webroot nicht beschreibbar)
  greift nur im klassischen Setup ohne separaten Deploy-Benutzer, wenn der
  Ausführende des interaktiven `./upgrade` sudo hat, aber den Webroot nicht
  besitzt; der Deploy-Benutzer braucht ihn nicht.

Hinweise:

- Der Deploy-Schlüssel gibt die Rechte des Deploy-Benutzers: Er kann den
  Checkout verändern und die Website (den Webroot) überschreiben oder
  verunstalten, braucht dafür aber kein root. Der Deploy-Benutzer darf daher
  keine sudo-Rechte haben (kein sudoers-Eintrag, nicht in der Gruppe `sudo`
  bzw. `wheel`), sonst ist die Isolation hinfällig.
- Der Admin führt `make` oder `./upgrade` niemals mit sudo in `<DEPLOY_PATH>`
  (oder in einem anderen Verzeichnis, das der Deploy-Benutzer beschreiben
  kann) aus, sonst ist die Isolation ebenfalls hinfällig. Ebenso führt der
  Admin im Admin-Clone weder `make deploy` noch `./upgrade` aus: `sudo rsync -a`
  würde den Webroot dem Admin übereignen und die automatischen Deployments
  brechen.
- Empfehlungen: dedizierter Deploy-Benutzer; der Schlüssel liegt nur als
  Repository-Secret und auf keiner anderen Maschine; `restrict` in
  `authorized_keys`; den Branch `main` per Branch Protection schützen und für
  den Deploy-Job optional ein GitHub-Environment mit Required Reviewers
  verwenden, denn jeder Push auf `main` wird als dieser Benutzer gebaut und
  veröffentlicht.

Lizenz / Herkunft
-----------------

Teile dieses Projekts basieren auf der ysap-Website von Dave Eddy
(https://github.com/bahamas10/ysap, MIT). Details, Dateiliste und Lizenztext
stehen in [NOTICE](NOTICE).
