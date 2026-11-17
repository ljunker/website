#!/usr/bin/env python3
"""Dienst für Terminanfragen von kryptikk.de (nur Python-Standardbibliothek).

Öffentlich:  POST /termin-api/anfrage      nimmt eine Terminanfrage entgegen
Dashboard:   /termin-admin/                passwortgeschützt, Anfragen ansehen
                                           und per Mail beantworten

Hinter nginx; lauscht standardmäßig nur auf 127.0.0.1:18090. Die
Konfiguration kommt aus Umgebungsvariablen bzw. einer Env-Datei (siehe
env.example und README). Lokal: `python3 termin/app.py --dev` (oder
`make serve-termin`): Mails nur auf der Konsole, kein Secure-Cookie,
Entwicklungs-Datenbank termin/dev.sqlite3, Dashboard-Passwort "dev".

Statusregel bei Antworten: Annehmen setzt `angenommen`, Ablehnen `abgelehnt`.
Eine Freitext-Antwort setzt `beantwortet`, aber nur, wenn die Anfrage noch
`neu` ist; ein bereits gesetzter Status bleibt erhalten.
"""
import datetime as dt
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import smtplib
import sqlite3
import sys
import threading
import time
import urllib.parse
from contextlib import closing
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from zoneinfo import ZoneInfo
    BERLIN = ZoneInfo("Europe/Berlin")
except Exception:  # tzdata fehlt: lokale Zeit des Servers verwenden
    BERLIN = None

HERE = os.path.dirname(os.path.abspath(__file__))

# --- Grenzen -----------------------------------------------------------------

MAX_BODY_API = 16 * 1024
MAX_BODY_ADMIN = 64 * 1024
LIMITS = {"name": 100, "email": 200, "club": 200, "ort": 200, "nachricht": 4000}
RATE_LIMIT_COUNT = 5            # Anfragen pro IP ...
RATE_LIMIT_SECONDS = 3600       # ... in diesem Zeitraum
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 900
SESSION_SECONDS = 12 * 3600
HONEYPOT = "hp_website"

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
CTRL_TEXT_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

STATUS_OFFEN = ("neu",)
STATUS_ERLEDIGT = ("angenommen", "abgelehnt", "beantwortet")
ARTEN = {"annehmen": "angenommen", "ablehnen": "abgelehnt", "freitext": "beantwortet"}
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS anfragen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    erstellt TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    wunschtermin TEXT NOT NULL,
    club TEXT NOT NULL DEFAULT '',
    ort TEXT NOT NULL DEFAULT '',
    nachricht TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'neu'
        CHECK (status IN ('neu', 'angenommen', 'abgelehnt', 'beantwortet')),
    ip TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS antworten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anfrage_id INTEGER NOT NULL REFERENCES anfragen(id),
    gesendet TEXT NOT NULL,
    art TEXT NOT NULL CHECK (art IN ('annehmen', 'ablehnen', 'freitext')),
    betreff TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    csrf TEXT NOT NULL,
    ablauf INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anfragen_ip ON anfragen(ip, erstellt);
"""


# --- Konfiguration -----------------------------------------------------------

def parse_env_file(path):
    """Liest KEY=VALUE-Zeilen (Kommentare mit #, optionale Anführungszeichen)."""
    values = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    return values


def truthy(value):
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


class Config:
    def __init__(self, values):
        g = values.get
        self.db = g("TERMIN_DB") or "/var/lib/kryptikk-termin/termin.sqlite3"
        self.host = g("TERMIN_HOST") or "127.0.0.1"
        self.port = int(g("TERMIN_PORT") or 18090)
        self.smtp_host = g("SMTP_HOST", "")
        self.smtp_port = int(g("SMTP_PORT") or 587)
        self.smtp_user = g("SMTP_USER", "")
        self.smtp_password = g("SMTP_PASSWORD", "")
        self.smtp_security = (g("SMTP_SECURITY") or "starttls").lower()
        self.mail_from = g("MAIL_FROM", "")
        self.notify_to = g("NOTIFY_TO", "")
        self.admin_password_hash = g("ADMIN_PASSWORD_HASH", "")
        self.secret_key = g("SECRET_KEY") or secrets.token_hex(32)
        self.mail_backend = (g("MAIL_BACKEND") or "smtp").lower()
        self.cookie_secure = truthy(g("COOKIE_SECURE", "1"))
        self.public_base_url = (g("PUBLIC_BASE_URL") or "https://kryptikk.de").rstrip("/")

    def problems(self):
        """Liste fehlender Pflichtangaben (leer = ok)."""
        out = []
        if self.mail_backend not in ("smtp", "console"):
            out.append("MAIL_BACKEND muss smtp oder console sein")
        if self.smtp_security not in ("starttls", "ssl"):
            out.append("SMTP_SECURITY muss starttls oder ssl sein")
        if self.mail_backend == "smtp":
            for name in ("SMTP_HOST", "MAIL_FROM", "NOTIFY_TO"):
                if not getattr(self, name.lower()):
                    out.append(name + " fehlt")
        if not self.admin_password_hash:
            out.append("ADMIN_PASSWORD_HASH fehlt (Login nicht möglich)")
        return out


def load_config(dev=False, environ=None):
    environ = os.environ if environ is None else environ
    values = {}
    if dev:
        values.update({
            "MAIL_BACKEND": "console",
            "COOKIE_SECURE": "0",
            "TERMIN_DB": os.path.join(HERE, "dev.sqlite3"),
            "PUBLIC_BASE_URL": "http://localhost:8000",
            "MAIL_FROM": "caller@example.invalid",
            "NOTIFY_TO": "caller@example.invalid",
        })
    candidates = [environ["TERMIN_ENV"]] if environ.get("TERMIN_ENV") else [
        "/etc/kryptikk-termin.env", os.path.join(HERE, ".env")]
    for path in candidates:
        # nicht lesbare Datei (z. B. root/600 beim Dienstbenutzer) überspringen:
        # die Werte kommen dann schon per EnvironmentFile in der Umgebung
        if os.path.isfile(path) and os.access(path, os.R_OK):
            try:
                values.update(parse_env_file(path))
            except OSError:
                continue
            break
    values.update({k: v for k, v in environ.items() if k.isupper()})
    if dev and not values.get("ADMIN_PASSWORD_HASH"):
        values["ADMIN_PASSWORD_HASH"] = hash_password("dev")
        print("Dev-Modus: Dashboard-Passwort ist 'dev'", file=sys.stderr)
    return Config(values)


# --- Passwort-Hash -----------------------------------------------------------

def hash_password(password, n=2 ** 14, r=8, p=1):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                            maxmem=128 * 1024 * 1024, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (n, r, p, salt.hex(), digest.hex())


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                                n=int(n), r=int(r), p=int(p),
                                maxmem=128 * 1024 * 1024, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# --- Mail --------------------------------------------------------------------

class ConsoleMailer:
    """Gibt Mails nur auf stdout aus (lokale Entwicklung)."""

    def send(self, msg):
        print("---------- Mail (console) ----------")
        print(msg.as_string())
        print("------------------------------------", flush=True)


class SmtpMailer:
    def __init__(self, config):
        self.c = config

    def send(self, msg):
        c = self.c
        if c.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(c.smtp_host, c.smtp_port, timeout=20)
        else:
            smtp = smtplib.SMTP(c.smtp_host, c.smtp_port, timeout=20)
        with smtp:
            if c.smtp_security == "starttls":
                smtp.starttls()
            if c.smtp_user:
                smtp.login(c.smtp_user, c.smtp_password)
            smtp.send_message(msg)


def build_mail(config, to, subject, body, reply_to):
    msg = EmailMessage()
    msg["From"] = config.mail_from
    msg["To"] = to
    msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    domain = config.mail_from.rpartition("@")[2] or "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(body)
    return msg


# --- Hilfsfunktionen ---------------------------------------------------------

def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def berlin_dt(ts):
    return dt.datetime.fromtimestamp(ts, BERLIN) if BERLIN else dt.datetime.fromtimestamp(ts)


def fmt_erstellt(value):
    try:
        t = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        t = t.astimezone(BERLIN) if BERLIN else t.astimezone()
        return t.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


def fmt_termin(value):
    """'2026-12-05 19:30' -> 'Sa 05.12.2026, 19:30 Uhr'."""
    try:
        t = dt.datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return value
    return "%s %s, %s Uhr" % (WOCHENTAGE[t.weekday()], t.strftime("%d.%m.%Y"), t.strftime("%H:%M"))


def clean_line(value):
    return value.strip() if isinstance(value, str) else ""


def clean_text(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return CTRL_TEXT_RE.sub("", value).strip()


def validate_anfrage(data, now):
    """Gibt (werte, fehler) zurück; fehler ist ein dict feld -> Meldung."""
    v = {k: clean_line(data.get(k)) for k in ("name", "email", "datum", "uhrzeit", "club", "ort")}
    v["nachricht"] = clean_text(data.get("nachricht"))
    errors = {}

    for key in ("name", "email", "club", "ort"):
        if CTRL_RE.search(v[key]):
            errors[key] = "Bitte keine Zeilenumbrüche oder Steuerzeichen verwenden."
    for key in ("name", "email", "nachricht"):
        if not v[key] and key not in errors:
            errors[key] = "Bitte ausfüllen."
    for key, limit in LIMITS.items():
        if len(v[key]) > limit and key not in errors:
            errors[key] = "Maximal %d Zeichen." % limit
    if v["email"] and "email" not in errors and not EMAIL_RE.match(v["email"]):
        errors["email"] = "Bitte eine gültige E-Mail-Adresse angeben."

    wunsch = ""
    if not v["datum"]:
        errors["datum"] = "Bitte ein Datum angeben."
    if not v["uhrzeit"]:
        errors["uhrzeit"] = "Bitte eine Uhrzeit angeben."
    if v["datum"] and v["uhrzeit"]:
        try:
            t = dt.datetime.strptime(v["datum"] + " " + v["uhrzeit"], "%Y-%m-%d %H:%M")
            current = berlin_dt(now).replace(tzinfo=None)
            if t <= current:
                errors["datum"] = "Der Wunschtermin muss in der Zukunft liegen."
            else:
                wunsch = t.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            errors["datum"] = "Bitte Datum und Uhrzeit prüfen."
    v["wunschtermin"] = wunsch
    return v, errors


def default_reply(art, row):
    """Vorbelegter Betreff und Text für eine Antwort (deutsche Standardtexte)."""
    termin = fmt_termin(row["wunschtermin"])
    club = (" für " + row["club"]) if row["club"] else ""
    subject = "Re: Deine Terminanfrage für %s" % termin
    if art == "annehmen":
        text = (
            "Hallo %s,\n\nvielen Dank für deine Anfrage%s. Der Termin am %s passt bei mir, "
            "ich sage gerne zu.\n\nAlles Weitere besprechen wir am besten direkt per Mail. "
            "Schick mir dazu gern noch ein paar Details zum Ablauf.\n\nViele Grüße\nLars"
            % (row["name"], club, termin))
    elif art == "ablehnen":
        text = (
            "Hallo %s,\n\nvielen Dank für deine Anfrage%s. Leider kann ich den Termin am %s "
            "nicht übernehmen.\n\nIch wünsche dir trotzdem eine tolle Veranstaltung und "
            "freue mich, wenn du bei Gelegenheit wieder an mich denkst.\n\nViele Grüße\nLars"
            % (row["name"], club, termin))
    else:
        text = ""
    return subject, text


# --- HTML --------------------------------------------------------------------

e = html.escape

ADMIN_CSS = """
.adm { max-width: 800px; margin: 0 auto; padding: 0 6px 40px; }
.adm h1 { margin: 16px 0 14px; color: var(--color3); }
.adm .bar { display: flex; justify-content: space-between; align-items: center; gap: 12px;
  border-bottom: 1px solid #87ff8755; padding: 10px 0; margin-bottom: 16px; flex-wrap: wrap; }
.adm .bar form { display: inline; }
.adm .submit-row { margin-top: 16px; }
.adm .filter a { padding: 2px 8px; border: 1px solid transparent; }
.adm .filter a.active { border-color: var(--color3); color: var(--color3); }
.adm table { width: 100%; border-collapse: collapse; }
.adm th, .adm td { padding: 8px 10px; text-align: left; vertical-align: top; }
.adm td { overflow-wrap: anywhere; }
.adm dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 14px; margin-bottom: 18px; }
.adm dt { color: var(--color4); }
.adm dd { overflow-wrap: anywhere; }
.adm .pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.adm .badge { display: inline-block; padding: 0 8px; border: 1px solid; border-radius: 3px; }
.adm .badge-neu { color: var(--color5); }
.adm .badge-angenommen { color: var(--color3); }
.adm .badge-abgelehnt { color: var(--color2); }
.adm .badge-beantwortet { color: var(--color1); }
.adm .msg { padding: 8px 12px; margin-bottom: 16px; border: 1px solid; border-radius: 3px; }
.adm .msg.ok { color: var(--color3); }
.adm .msg.err { color: var(--color2); }
.adm .reply { border: 1px solid #87ff8755; border-radius: 3px; padding: 10px 12px; margin-bottom: 12px; }
.adm .reply h3 { color: var(--color3); margin-bottom: 6px; }
.adm .actions { display: flex; gap: 10px; flex-wrap: wrap; margin: 18px 0; }
.adm label { display: block; margin: 12px 0 4px; color: var(--color4); }
.adm input[type=text], .adm input[type=password], .adm textarea { width: 100%; box-sizing: border-box;
  font: inherit; color: var(--color5); background: #111; border: 1px solid #87ff8755;
  border-radius: 3px; padding: 6px 8px; }
.adm textarea { min-height: 280px; resize: vertical; }
.adm button, .adm .btn { font: inherit; color: var(--color3); background: transparent;
  border: 1px solid var(--color3); border-radius: 3px; padding: 5px 12px; cursor: pointer; display: inline-block; }
.adm button:hover, .adm .btn:hover { color: var(--color4); border-color: var(--color4); }
.adm .linklike { border: 0; padding: 0; color: var(--color1); }
@media (max-width: 650px) { .adm th.hide-m, .adm td.hide-m { display: none; } }
"""


def layout(title, body, nav=True, csrf=""):
    bar = ""
    if nav:
        bar = (
            '<div class="bar"><span><a href="/termin-admin/">terminanfragen</a></span>'
            '<form method="post" action="/termin-admin/logout">'
            '<input type="hidden" name="csrf" value="%s">'
            '<button class="linklike" type="submit">abmelden</button></form></div>' % e(csrf))
    return (
        '<!doctype html>\n<html lang="de"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<meta name="robots" content="noindex, nofollow">'
        '<title>%s | terminanfragen</title>'
        '<link rel="stylesheet" href="/static/style.css">'
        '<link rel="stylesheet" href="/termin-admin/admin.css"></head>'
        '<body><div class="adm">%s%s</div></body></html>\n' % (e(title), bar, body))


def public_page(title, body):
    return (
        '<!doctype html>\n<html lang="de"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<meta name="robots" content="noindex"><title>%s | Lars Junker</title>'
        '<link rel="stylesheet" href="/static/style.css"></head>'
        '<body><div id="container"><main><h1 class="title">%s</h1>%s</main></div></body></html>\n'
        % (e(title), e(title), body))


def badge(status):
    return '<span class="badge badge-%s">%s</span>' % (e(status), e(status))


def render_login(token, error=""):
    err = '<div class="msg err">%s</div>' % e(error) if error else ""
    body = (
        '<h1>anmelden</h1>%s<form method="post" action="/termin-admin/login">'
        '<input type="hidden" name="csrf" value="%s">'
        '<label for="pw">Passwort</label>'
        '<input id="pw" type="password" name="password" autocomplete="current-password" required autofocus>'
        '<p class="submit-row"><button type="submit">anmelden</button></p></form>'
        % (err, e(token)))
    return layout("Anmelden", body, nav=False)


def render_list(rows, flt, csrf):
    def tab(key, label):
        cls = ' class="active"' if key == flt else ""
        return '<a href="/termin-admin/?filter=%s"%s>%s</a>' % (key, cls, label)

    lines = []
    for r in rows:
        lines.append(
            '<tr><td><a href="/termin-admin/anfrage/%d">%s</a></td><td>%s</td>'
            '<td class="hide-m">%s</td><td>%s</td></tr>' % (
                r["id"], e(fmt_termin(r["wunschtermin"])), e(r["name"]),
                e(r["club"] or "–"), badge(r["status"])))
    if lines:
        table = ('<table><tr><th>Wunschtermin</th><th>Name</th><th class="hide-m">Club</th>'
                 '<th>Status</th></tr>%s</table>' % "".join(lines))
    else:
        table = "<p>Keine Anfragen.</p>"
    body = ('<h1>terminanfragen</h1><p class="filter">%s %s %s</p><br>%s' % (
        tab("offen", "offen"), tab("erledigt", "erledigt"), tab("alle", "alle"), table))
    return layout("Anfragen", body, csrf=csrf)


def render_detail(row, antworten, csrf, notice=""):
    msg = '<div class="msg ok">%s</div>' % e(notice) if notice else ""
    fields = [
        ("Status", badge(row["status"])),
        ("Eingegangen", e(fmt_erstellt(row["erstellt"]))),
        ("Name", e(row["name"])),
        ("E-Mail", '<a href="mailto:%s">%s</a>' % (e(row["email"]), e(row["email"]))),
        ("Wunschtermin", e(fmt_termin(row["wunschtermin"]))),
        ("Club", e(row["club"] or "–")),
        ("Ort", e(row["ort"] or "–")),
    ]
    dl = "".join("<dt>%s</dt><dd>%s</dd>" % (k, v) for k, v in fields)
    base = "/termin-admin/anfrage/%d/antwort?art=" % row["id"]
    actions = (
        '<div class="actions"><a class="btn" href="%sannehmen">annehmen</a>'
        '<a class="btn" href="%sablehnen">ablehnen</a>'
        '<a class="btn" href="%sfreitext">antworten</a></div>' % (base, base, base))
    replies = ""
    for a in antworten:
        replies += (
            '<div class="reply"><h3>%s, %s</h3><p><strong>%s</strong></p><p class="pre">%s</p></div>'
            % (e(a["art"]), e(fmt_erstellt(a["gesendet"])), e(a["betreff"]), e(a["text"])))
    body = (
        '%s<h1>anfrage von %s</h1><dl>%s</dl><h3>Nachricht</h3><p class="pre">%s</p>%s'
        '<h3>Gesendete Antworten</h3>%s<p><a href="/termin-admin/">&laquo; zur Übersicht</a></p>'
        % (msg, e(row["name"]), dl, e(row["nachricht"]), actions,
           replies or "<p>Noch keine Antwort gesendet.</p>"))
    return layout("Anfrage %d" % row["id"], body, csrf=csrf)


def render_reply_form(row, art, subject, text, csrf, error=""):
    err = '<div class="msg err">%s</div>' % e(error) if error else ""
    titel = {"annehmen": "annehmen", "ablehnen": "ablehnen", "freitext": "antworten"}[art]
    body = (
        '<h1>%s: %s</h1>%s<p>An: %s</p>'
        '<form method="post" action="/termin-admin/anfrage/%d/antwort">'
        '<input type="hidden" name="csrf" value="%s"><input type="hidden" name="art" value="%s">'
        '<label for="betreff">Betreff</label>'
        '<input id="betreff" type="text" name="betreff" value="%s" maxlength="200" required>'
        '<label for="text">Text</label>'
        '<textarea id="text" name="text" maxlength="10000" required>%s</textarea>'
        '<p class="submit-row"><button type="submit">mail senden</button> '
        '<a href="/termin-admin/anfrage/%d">abbrechen</a></p></form>'
        % (e(titel), e(row["name"]), err, e(row["email"]), row["id"], e(csrf), e(art),
           e(subject), e(text), row["id"]))
    return layout("Antwort", body, csrf=csrf)


# --- Anwendung ---------------------------------------------------------------

class App:
    def __init__(self, config, mailer, clock=time.time):
        self.config = config
        self.mailer = mailer
        self.clock = clock
        self.login_state = {}  # ip -> [fehlversuche, gesperrt_bis]
        self.lock = threading.Lock()
        with closing(self.connect()) as db:
            db.executescript(SCHEMA)
            db.commit()

    def connect(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.config.db)), exist_ok=True)
        db = sqlite3.connect(self.config.db, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    # Login-Token (zustandslos, nur für das Login-Formular)
    def login_token(self):
        ts = str(int(self.clock()))
        mac = hmac.new(self.config.secret_key.encode(), ("login" + ts).encode(), "sha256").hexdigest()
        return ts + "." + mac

    def login_token_ok(self, token):
        ts, _, mac = token.partition(".")
        if not ts.isdigit():
            return False
        good = hmac.new(self.config.secret_key.encode(), ("login" + ts).encode(), "sha256").hexdigest()
        return hmac.compare_digest(mac, good) and 0 <= self.clock() - int(ts) < 3600

    def locked(self, ip):
        with self.lock:
            state = self.login_state.get(ip)
            return bool(state and state[1] > self.clock())

    def login_failed(self, ip):
        with self.lock:
            state = self.login_state.setdefault(ip, [0, 0])
            if state[1] and state[1] <= self.clock():
                state[0], state[1] = 0, 0
            state[0] += 1
            if state[0] >= LOGIN_MAX_FAILS:
                state[1] = self.clock() + LOGIN_LOCK_SECONDS
                state[0] = 0

    def login_ok(self, ip):
        with self.lock:
            self.login_state.pop(ip, None)

    def create_session(self):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = int(self.clock())
        with closing(self.connect()) as db:
            db.execute("DELETE FROM sessions WHERE ablauf < ?", (now,))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                       (hashlib.sha256(token.encode()).hexdigest(), csrf, now + SESSION_SECONDS))
            db.commit()
        return token, csrf

    def get_session(self, token):
        """Gibt das CSRF-Token der gültigen Session zurück, sonst None."""
        if not token:
            return None
        with closing(self.connect()) as db:
            row = db.execute("SELECT csrf, ablauf FROM sessions WHERE token_hash = ?",
                             (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row and row["ablauf"] >= self.clock():
            return row["csrf"]
        return None

    def delete_session(self, token):
        if token:
            with closing(self.connect()) as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?",
                           (hashlib.sha256(token.encode()).hexdigest(),))
                db.commit()

    def rate_limited(self, db, ip):
        since = iso(self.clock() - RATE_LIMIT_SECONDS)
        n = db.execute("SELECT COUNT(*) FROM anfragen WHERE ip = ? AND erstellt > ?",
                       (ip, since)).fetchone()[0]
        return n >= RATE_LIMIT_COUNT

    def notify(self, anfrage_id, v):
        c = self.config
        body = (
            "Neue Terminanfrage über kryptikk.de\n\n"
            "Name:         %s\nE-Mail:       %s\nWunschtermin: %s\nClub:         %s\nOrt:          %s\n\n"
            "Nachricht:\n%s\n\nDashboard: %s/termin-admin/anfrage/%d\n"
            % (v["name"], v["email"], fmt_termin(v["wunschtermin"]), v["club"] or "-",
               v["ort"] or "-", v["nachricht"], c.public_base_url, anfrage_id))
        msg = build_mail(c, c.notify_to, "Neue Terminanfrage von %s" % v["name"], body, v["email"])
        self.mailer.send(msg)

    def create_anfrage(self, data, ip):
        """Gibt (http_status, json) zurück."""
        if clean_line(data.get(HONEYPOT)):
            return 200, {"ok": True}  # Bot: so tun als ob, nichts speichern
        v, errors = validate_anfrage(data, self.clock())
        if errors:
            return 400, {"ok": False, "fehler": errors}
        with closing(self.connect()) as db:
            if self.rate_limited(db, ip):
                return 429, {"ok": False, "fehler": {"allgemein": "Zu viele Anfragen, bitte später erneut versuchen."}}
            cur = db.execute(
                "INSERT INTO anfragen (erstellt, name, email, wunschtermin, club, ort, nachricht, ip) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (iso(self.clock()), v["name"], v["email"], v["wunschtermin"], v["club"], v["ort"],
                 v["nachricht"], ip))
            db.commit()
            anfrage_id = cur.lastrowid
        try:
            self.notify(anfrage_id, v)
        except Exception as exc:  # die Anfrage ist gespeichert, Mailfehler nur loggen
            print("Benachrichtigungsmail fehlgeschlagen (Anfrage %d): %r" % (anfrage_id, exc),
                  file=sys.stderr, flush=True)
        return 201, {"ok": True}

    def send_reply(self, anfrage_id, art, subject, text):
        """Sendet die Antwort und aktualisiert Status/Antworten. Wirft bei Mailfehler."""
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM anfragen WHERE id = ?", (anfrage_id,)).fetchone()
            msg = build_mail(self.config, row["email"], subject, text, self.config.mail_from)
            self.mailer.send(msg)  # bei Fehler: nichts gespeichert, Status unverändert
            neu = ARTEN[art]
            if art == "freitext" and row["status"] != "neu":
                neu = row["status"]
            db.execute("INSERT INTO antworten (anfrage_id, gesendet, art, betreff, text) "
                       "VALUES (?, ?, ?, ?, ?)",
                       (anfrage_id, iso(self.clock()), art, subject, text))
            db.execute("UPDATE anfragen SET status = ? WHERE id = ?", (neu, anfrage_id))
            db.commit()


# --- HTTP --------------------------------------------------------------------

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "Content-Security-Policy": ("default-src 'none'; style-src 'self'; font-src 'self'; "
                                "img-src 'self'; form-action 'self'; base-uri 'none'; "
                                "frame-ancestors 'none'"),
}

ANFRAGE_RE = re.compile(r"^/termin-admin/anfrage/(\d+)(/antwort)?$")


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "termin"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        # --- Ausgabe ---
        def send_body(self, status, body, ctype, headers=None):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            for k, v in (headers or []):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def send_html(self, status, body, headers=None):
            self.send_body(status, body, "text/html; charset=utf-8", headers)

        def send_json(self, status, obj):
            self.send_body(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

        def redirect(self, location, headers=None):
            self.send_body(303, "", "text/plain; charset=utf-8", [("Location", location)] + (headers or []))

        def not_found(self):
            self.send_html(404, public_page("nicht gefunden", "<p>Diese Seite gibt es nicht.</p>"))

        # --- Eingabe ---
        def client_ip(self):
            return self.headers.get("X-Real-IP", "").strip() or self.client_address[0]

        def read_body(self, limit):
            """Gibt den Body (bytes) zurück oder None, wenn schon geantwortet wurde."""
            length = self.headers.get("Content-Length")
            if length is None or not length.isdigit():
                self.close_connection = True
                self.send_json(411, {"ok": False, "fehler": {"allgemein": "Content-Length fehlt."}})
                return None
            if int(length) > limit:
                self.close_connection = True
                self.send_json(413, {"ok": False, "fehler": {"allgemein": "Anfrage zu groß."}})
                return None
            return self.rfile.read(int(length))

        def form_data(self, body):
            parsed = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            return {k: v[0] for k, v in parsed.items()}

        def session_token(self):
            jar = cookies.SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
            except cookies.CookieError:
                return ""
            morsel = jar.get("termin_session")
            return morsel.value if morsel else ""

        def cookie_header(self, token, max_age):
            parts = ["termin_session=%s" % token, "Path=/termin-admin/", "HttpOnly",
                     "SameSite=Strict", "Max-Age=%d" % max_age]
            if app.config.cookie_secure:
                parts.append("Secure")
            return ("Set-Cookie", "; ".join(parts))

        def auth(self):
            """CSRF-Token der gültigen Session oder None (dann wurde bereits umgeleitet)."""
            csrf = app.get_session(self.session_token())
            if csrf is None:
                self.redirect("/termin-admin/login")
            return csrf

        def csrf_ok(self, csrf, data):
            return hmac.compare_digest(str(data.get("csrf", "")), csrf)

        def forbidden(self):
            self.send_html(403, public_page("verboten", "<p>Ungültiges Sicherheitstoken.</p>"))

        # --- Routing ---
        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            path, query = url.path, urllib.parse.parse_qs(url.query)
            try:
                self.route_get(path, query)
            except Exception as exc:
                self.fail(exc)

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            try:
                self.route_post(path)
            except Exception as exc:
                self.fail(exc)

        def fail(self, exc):
            print("Fehler: %r" % (exc,), file=sys.stderr, flush=True)
            self.close_connection = True
            try:
                self.send_html(500, public_page("fehler", "<p>Interner Fehler.</p>"))
            except OSError:
                pass

        def route_get(self, path, query):
            if path == "/termin-api/health":
                return self.send_json(200, {"ok": True})
            if path == "/termin-admin":
                return self.redirect("/termin-admin/")
            if path == "/termin-admin/admin.css":
                return self.send_body(200, ADMIN_CSS, "text/css; charset=utf-8")
            if path == "/termin-admin/login":
                if app.get_session(self.session_token()) is not None:
                    return self.redirect("/termin-admin/")
                return self.send_html(200, render_login(app.login_token()))
            if path == "/termin-admin/":
                csrf = self.auth()
                if csrf is None:
                    return
                return self.page_list(csrf, query)
            m = ANFRAGE_RE.match(path)
            if m:
                csrf = self.auth()
                if csrf is None:
                    return
                if m.group(2):
                    return self.page_reply(csrf, int(m.group(1)), query.get("art", [""])[0])
                return self.page_detail(csrf, int(m.group(1)), query.get("ok") == ["1"])
            self.not_found()

        def route_post(self, path):
            if path == "/termin-api/anfrage":
                return self.post_anfrage()
            if path == "/termin-admin/login":
                return self.post_login()
            if path == "/termin-admin/logout":
                return self.post_logout()
            m = ANFRAGE_RE.match(path)
            if m and m.group(2):
                return self.post_reply(int(m.group(1)))
            self.not_found()

        # --- API ---
        def post_anfrage(self):
            body = self.read_body(MAX_BODY_API)
            if body is None:
                return
            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            is_json = ctype == "application/json"
            if is_json:
                try:
                    data = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    data = None
                if not isinstance(data, dict):
                    return self.send_json(400, {"ok": False, "fehler": {"allgemein": "Ungültige Daten."}})
            elif ctype == "application/x-www-form-urlencoded":
                data = self.form_data(body)
            else:
                return self.send_json(415, {"ok": False, "fehler": {"allgemein": "Content-Type nicht unterstützt."}})
            status, result = app.create_anfrage(data, self.client_ip())
            if is_json:
                return self.send_json(status, result)
            if result["ok"]:
                return self.send_html(200, public_page(
                    "danke", "<p>Deine Anfrage ist angekommen. Ich melde mich bei dir.</p>"
                             '<p><a href="/schedule">&laquo; zu den calltermine</a></p>'))
            items = "".join("<li>%s</li>" % e(m) for m in result["fehler"].values())
            self.send_html(status, public_page(
                "fehler", "<ul>%s</ul><p><a href=\"/terminanfrage\">&laquo; zurück zum Formular</a></p>" % items))

        # --- Login ---
        def post_login(self):
            body = self.read_body(MAX_BODY_ADMIN)
            if body is None:
                return
            data = self.form_data(body)
            ip = self.client_ip()
            if not app.login_token_ok(data.get("csrf", "")):
                return self.send_html(403, render_login(app.login_token(), "Formular abgelaufen, bitte erneut versuchen."))
            if app.locked(ip):
                return self.send_html(429, render_login(app.login_token(), "Zu viele Fehlversuche, bitte später erneut versuchen."))
            stored = app.config.admin_password_hash
            if stored and verify_password(data.get("password", ""), stored):
                app.login_ok(ip)
                token, _ = app.create_session()
                return self.redirect("/termin-admin/", [self.cookie_header(token, SESSION_SECONDS)])
            app.login_failed(ip)
            self.send_html(401, render_login(app.login_token(), "Passwort falsch."))

        def post_logout(self):
            body = self.read_body(MAX_BODY_ADMIN)
            if body is None:
                return
            token = self.session_token()
            csrf = app.get_session(token)
            if csrf is None:
                return self.redirect("/termin-admin/login")
            if not self.csrf_ok(csrf, self.form_data(body)):
                return self.forbidden()
            app.delete_session(token)
            self.redirect("/termin-admin/login", [self.cookie_header("", 0)])

        # --- Dashboard ---
        def page_list(self, csrf, query):
            flt = query.get("filter", ["offen"])[0]
            if flt not in ("offen", "erledigt", "alle"):
                flt = "offen"
            sql = "SELECT * FROM anfragen"
            params = ()
            if flt != "alle":
                statuses = STATUS_OFFEN if flt == "offen" else STATUS_ERLEDIGT
                sql += " WHERE status IN (%s)" % ",".join("?" * len(statuses))
                params = statuses
            sql += " ORDER BY id DESC"
            with closing(app.connect()) as db:
                rows = db.execute(sql, params).fetchall()
            self.send_html(200, render_list(rows, flt, csrf))

        def load(self, anfrage_id):
            with closing(app.connect()) as db:
                row = db.execute("SELECT * FROM anfragen WHERE id = ?", (anfrage_id,)).fetchone()
                antworten = db.execute("SELECT * FROM antworten WHERE anfrage_id = ? ORDER BY id",
                                       (anfrage_id,)).fetchall()
            return row, antworten

        def page_detail(self, csrf, anfrage_id, sent):
            row, antworten = self.load(anfrage_id)
            if row is None:
                return self.not_found()
            self.send_html(200, render_detail(row, antworten, csrf, "Mail gesendet." if sent else ""))

        def page_reply(self, csrf, anfrage_id, art):
            row, _ = self.load(anfrage_id)
            if row is None or art not in ARTEN:
                return self.not_found()
            subject, text = default_reply(art, row)
            self.send_html(200, render_reply_form(row, art, subject, text, csrf))

        def post_reply(self, anfrage_id):
            body = self.read_body(MAX_BODY_ADMIN)
            if body is None:
                return
            csrf = self.auth()
            if csrf is None:
                return
            data = self.form_data(body)
            if not self.csrf_ok(csrf, data):
                return self.forbidden()
            row, _ = self.load(anfrage_id)
            art = data.get("art", "")
            if row is None or art not in ARTEN:
                return self.not_found()
            subject = data.get("betreff", "").strip()
            text = clean_text(data.get("text", ""))
            error = ""
            if not subject or CTRL_RE.search(subject) or len(subject) > 200:
                error = "Betreff fehlt, ist zu lang oder enthält Zeilenumbrüche."
            elif not text or len(text) > 10000:
                error = "Text fehlt oder ist zu lang."
            else:
                try:
                    app.send_reply(anfrage_id, art, subject, text)
                except Exception as exc:
                    print("Antwortmail fehlgeschlagen (Anfrage %d): %r" % (anfrage_id, exc),
                          file=sys.stderr, flush=True)
                    error = "Die Mail konnte nicht gesendet werden. Es wurde nichts geändert."
            if error:
                return self.send_html(502 if "gesendet" in error else 400,
                                      render_reply_form(row, art, subject, text, csrf, error))
            self.redirect("/termin-admin/anfrage/%d?ok=1" % anfrage_id)

        def log_message(self, fmt, *args):
            sys.stderr.write("%s - %s\n" % (self.client_address[0], fmt % args))

    return Handler


def make_server(config, mailer, clock=time.time):
    app = App(config, mailer, clock)
    server = ThreadingHTTPServer((config.host, config.port), make_handler(app))
    server.daemon_threads = True
    server.app = app
    return server


def main():
    dev = "--dev" in sys.argv[1:]
    config = load_config(dev=dev)
    for problem in config.problems():
        print("Warnung: " + problem, file=sys.stderr)
    mailer = ConsoleMailer() if config.mail_backend == "console" else SmtpMailer(config)
    server = make_server(config, mailer)
    print("Terminanfragen auf http://%s:%d (Mail: %s, DB: %s)"
          % (config.host, config.port, config.mail_backend, config.db), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
