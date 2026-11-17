"""Tests für den Terminanfragen-Dienst (nur unittest, Mail-Backend gemockt).

Ausführen: make test   (python3 -m unittest discover -s termin)
"""
import datetime as dt
import http.client
import json
import os
import re
import shutil
import tempfile
import threading
import unittest
import urllib.parse

import app as termin


class FakeMailer:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, msg):
        if self.fail:
            raise OSError("SMTP kaputt")
        self.sent.append(msg)


class Clock:
    def __init__(self):
        self.t = dt.datetime(2026, 11, 17, 12, 0, tzinfo=dt.timezone.utc).timestamp()

    def __call__(self):
        return self.t


PASSWORD = "test-passwort-123"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mailer = FakeMailer()
        self.clock = Clock()
        config = termin.Config({
            "TERMIN_DB": os.path.join(self.tmp, "t.sqlite3"),
            "TERMIN_PORT": "0",
            "MAIL_FROM": "lars@example.invalid",
            "NOTIFY_TO": "notify@example.invalid",
            "ADMIN_PASSWORD_HASH": termin.hash_password(PASSWORD, n=2 ** 10),
            "SECRET_KEY": "test-secret",
            "COOKIE_SECURE": "1",
        })
        self.server = termin.make_server(config, self.mailer, self.clock)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.cookie = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def request(self, method, path, body=None, headers=None, form=None, cookie=True):
        headers = dict(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body)
            headers.setdefault("Content-Type", "application/json")
        if form is not None:
            body = urllib.parse.urlencode(form)
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        result = (resp.status, data, resp)
        conn.close()
        return result

    def valid(self, **override):
        data = {
            "name": "Erika Muster", "email": "erika@example.invalid",
            "datum": "2026-12-05", "uhrzeit": "19:30",
            "club": "Tanzclub <b>Linde</b>", "ort": "Musterstadt",
            "nachricht": "Hallo,\nhabt ihr Zeit?",
        }
        data.update(override)
        return data

    def post_anfrage(self, ip="10.0.0.1", **override):
        return self.request("POST", "/termin-api/anfrage", body=self.valid(**override),
                            headers={"X-Real-IP": ip})

    def login(self, password=PASSWORD, ip="10.1.1.1"):
        status, page, _ = self.request("GET", "/termin-admin/login", cookie=False)
        token = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        status, page, resp = self.request(
            "POST", "/termin-admin/login", form={"csrf": token, "password": password},
            headers={"X-Real-IP": ip}, cookie=False)
        set_cookie = resp.getheader("Set-Cookie")
        if status == 303 and set_cookie:
            self.cookie = set_cookie.split(";")[0]
        return status, set_cookie

    def csrf(self, path="/termin-admin/"):
        _, page, _ = self.request("GET", path)
        return re.search(r'name="csrf" value="([^"]+)"', page).group(1)

    def status_of(self, anfrage_id=1):
        with termin.closing(self.server.app.connect()) as db:
            return db.execute("SELECT status FROM anfragen WHERE id = ?", (anfrage_id,)).fetchone()[0]

    def count(self, table):
        with termin.closing(self.server.app.connect()) as db:
            return db.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]


class ConfigTest(unittest.TestCase):
    def test_nicht_lesbare_env_datei_wird_uebersprungen(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = os.path.join(tmp, "x.env")
        with open(path, "w") as f:
            f.write("SMTP_HOST=aus-datei\n")
        os.chmod(path, 0)
        if os.access(path, os.R_OK):
            self.skipTest("Datei trotz chmod 000 lesbar (root)")
        config = termin.load_config(environ={"TERMIN_ENV": path, "SMTP_HOST": "aus-umgebung"})
        self.assertEqual(config.smtp_host, "aus-umgebung")


class PasswordTest(unittest.TestCase):
    def test_roundtrip(self):
        h = termin.hash_password("geheim", n=2 ** 10)
        self.assertTrue(h.startswith("scrypt$1024$8$1$"))
        self.assertTrue(termin.verify_password("geheim", h))
        self.assertFalse(termin.verify_password("falsch", h))
        self.assertFalse(termin.verify_password("geheim", "kaputt"))


class AnfrageTest(Base):
    def test_ok_speichert_und_benachrichtigt(self):
        status, body, _ = self.post_anfrage()
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body), {"ok": True})
        self.assertEqual(self.count("anfragen"), 1)
        self.assertEqual(len(self.mailer.sent), 1)
        msg = self.mailer.sent[0]
        self.assertEqual(msg["To"], "notify@example.invalid")
        self.assertEqual(msg["Reply-To"], "erika@example.invalid")
        self.assertIn("/termin-admin/anfrage/1", msg.get_content())

    def test_form_post_liefert_html(self):
        status, body, _ = self.request("POST", "/termin-api/anfrage", form=self.valid())
        self.assertEqual(status, 200)
        self.assertIn("danke", body)
        status, body, _ = self.request("POST", "/termin-api/anfrage", form=self.valid(name=""))
        self.assertEqual(status, 400)
        self.assertIn("Bitte ausfüllen", body)

    def test_validierung(self):
        cases = [
            ({"name": ""}, "name"), ({"email": "kein-mail"}, "email"),
            ({"nachricht": ""}, "nachricht"), ({"datum": ""}, "datum"),
            ({"uhrzeit": "25:99"}, "datum"), ({"datum": "2026-11-16"}, "datum"),
            ({"name": "A" * 101}, "name"), ({"nachricht": "x" * 4001}, "nachricht"),
            ({"name": "Eve\nBcc: x@example.invalid"}, "name"),
            ({"email": "a@example.invalid\r\nBcc: x@example.invalid"}, "email"),
        ]
        for override, field in cases:
            status, body, _ = self.post_anfrage(**override)
            self.assertEqual(status, 400, override)
            self.assertIn(field, json.loads(body)["fehler"], override)
        self.assertEqual(self.count("anfragen"), 0)
        self.assertEqual(self.mailer.sent, [])

    def test_club_ort_optional(self):
        status, _, _ = self.post_anfrage(club="", ort="")
        self.assertEqual(status, 201)

    def test_honeypot(self):
        status, body, _ = self.post_anfrage(hp_website="http://spam.invalid")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})
        self.assertEqual(self.count("anfragen"), 0)
        self.assertEqual(self.mailer.sent, [])

    def test_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.post_anfrage()[0], 201)
        self.assertEqual(self.post_anfrage()[0], 429)
        self.assertEqual(self.post_anfrage(ip="10.0.0.2")[0], 201)
        self.clock.t += 3601
        self.assertEqual(self.post_anfrage()[0], 201)

    def test_body_limit_und_ungueltig(self):
        status, _, _ = self.request("POST", "/termin-api/anfrage", body="x" * 20000,
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(status, 413)
        status, _, _ = self.request("POST", "/termin-api/anfrage", body="{kaputt",
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        status, _, _ = self.request("POST", "/termin-api/anfrage", body="[]",
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_mailfehler_verliert_anfrage_nicht(self):
        self.mailer.fail = True
        status, _, _ = self.post_anfrage()
        self.assertEqual(status, 201)
        self.assertEqual(self.count("anfragen"), 1)


class LoginTest(Base):
    def test_dashboard_braucht_login(self):
        for path in ("/termin-admin/", "/termin-admin/anfrage/1", "/termin-admin/anfrage/1/antwort?art=annehmen"):
            status, _, resp = self.request("GET", path)
            self.assertEqual(status, 303, path)
            self.assertEqual(resp.getheader("Location"), "/termin-admin/login")

    def test_login_richtig_und_cookie(self):
        status, cookie = self.login()
        self.assertEqual(status, 303)
        for flag in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/termin-admin/"):
            self.assertIn(flag, cookie)
        self.assertEqual(self.request("GET", "/termin-admin/")[0], 200)

    def test_login_falsch(self):
        status, cookie = self.login("falsch")
        self.assertEqual(status, 401)
        self.assertIsNone(cookie)
        self.assertEqual(self.request("GET", "/termin-admin/")[0], 303)

    def test_login_sperre(self):
        for _ in range(5):
            self.assertEqual(self.login("falsch")[0], 401)
        self.assertEqual(self.login(PASSWORD)[0], 429)  # auch richtig: gesperrt
        self.assertEqual(self.login(PASSWORD, ip="10.9.9.9")[0], 303)  # andere IP ok
        self.cookie = ""
        self.clock.t += 901
        self.assertEqual(self.login(PASSWORD)[0], 303)

    def test_login_csrf_pflicht(self):
        status, _, _ = self.request("POST", "/termin-admin/login",
                                    form={"csrf": "x", "password": PASSWORD}, cookie=False)
        self.assertEqual(status, 403)

    def test_session_laeuft_ab(self):
        self.login()
        self.clock.t += termin.SESSION_SECONDS + 1
        self.assertEqual(self.request("GET", "/termin-admin/")[0], 303)

    def test_logout(self):
        self.login()
        token = self.csrf()
        status, _, _ = self.request("POST", "/termin-admin/logout", form={"csrf": "falsch"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/termin-admin/logout", form={"csrf": token})
        self.assertEqual(status, 303)
        self.assertEqual(self.request("GET", "/termin-admin/")[0], 303)


class DashboardTest(Base):
    def setUp(self):
        super().setUp()
        self.post_anfrage()
        self.mailer.sent.clear()
        self.login()

    def reply(self, art, **override):
        token = self.csrf("/termin-admin/anfrage/1")
        form = {"csrf": token, "art": art, "betreff": "Re: Test", "text": "Hallo Erika"}
        form.update(override)
        return self.request("POST", "/termin-admin/anfrage/1/antwort", form=form)

    def test_security_header(self):
        _, _, resp = self.request("GET", "/termin-admin/")
        self.assertEqual(resp.getheader("X-Frame-Options"), "DENY")
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        self.assertIn("default-src 'none'", resp.getheader("Content-Security-Policy"))
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")

    def test_kein_inline_style_oder_script(self):
        pages = [self.request("GET", p)[1] for p in (
            "/termin-admin/", "/termin-admin/anfrage/1",
            "/termin-admin/anfrage/1/antwort?art=annehmen")]
        self.cookie = ""
        pages.append(self.request("GET", "/termin-admin/login")[1])
        for page in pages:
            self.assertNotRegex(page, r"(?i)\sstyle\s*=")
            self.assertNotRegex(page, r"(?i)<script")
            self.assertNotRegex(page, r"(?i)\son[a-z]+\s*=")

    def test_liste_filter_und_escaping(self):
        _, page, _ = self.request("GET", "/termin-admin/")
        self.assertIn("Erika Muster", page)
        self.assertNotIn("<b>Linde</b>", page)
        self.assertIn("&lt;b&gt;Linde&lt;/b&gt;", page)
        self.assertNotIn("Erika Muster", self.request("GET", "/termin-admin/?filter=erledigt")[1])
        self.assertIn("Erika Muster", self.request("GET", "/termin-admin/?filter=alle")[1])

    def test_detail_escaping(self):
        self.post_anfrage(name="<script>alert(1)</script>", nachricht="<img src=x onerror=1>")
        _, page, _ = self.request("GET", "/termin-admin/anfrage/2")
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;script&gt;", page)

    def test_vorbelegte_texte(self):
        _, page, _ = self.request("GET", "/termin-admin/anfrage/1/antwort?art=annehmen")
        self.assertIn("Hallo Erika Muster", page)
        self.assertIn("Sa 05.12.2026, 19:30 Uhr", page)
        self.assertIn("&lt;b&gt;Linde&lt;/b&gt;", page)
        _, page, _ = self.request("GET", "/termin-admin/anfrage/1/antwort?art=freitext")
        self.assertIn("Re: Deine Terminanfrage", page)
        self.assertEqual(self.request("GET", "/termin-admin/anfrage/1/antwort?art=quatsch")[0], 404)
        self.assertEqual(self.request("GET", "/termin-admin/anfrage/99")[0], 404)

    def test_annehmen_ablehnen_freitext(self):
        status, _, resp = self.reply("annehmen")
        self.assertEqual(status, 303)
        self.assertEqual(self.status_of(), "angenommen")
        msg = self.mailer.sent[-1]
        self.assertEqual(msg["To"], "erika@example.invalid")
        self.assertEqual(msg["From"], "lars@example.invalid")
        self.assertEqual(msg["Reply-To"], "lars@example.invalid")
        self.assertEqual(msg["Subject"], "Re: Test")
        self.assertIn("Hallo Erika", msg.get_content())
        self.assertIsNotNone(msg["Date"])
        self.assertIsNotNone(msg["Message-ID"])
        # Freitext lässt vorhandenen Status unangetastet
        self.reply("freitext")
        self.assertEqual(self.status_of(), "angenommen")
        self.reply("ablehnen")
        self.assertEqual(self.status_of(), "abgelehnt")
        self.assertEqual(self.count("antworten"), 3)
        _, page, _ = self.request("GET", "/termin-admin/anfrage/1")
        self.assertIn("Hallo Erika", page)

    def test_freitext_bei_neu_setzt_beantwortet(self):
        self.reply("freitext")
        self.assertEqual(self.status_of(), "beantwortet")

    def test_csrf_pflicht(self):
        status, _, _ = self.reply("annehmen", csrf="falsch")
        self.assertEqual(status, 403)
        self.assertEqual(self.status_of(), "neu")
        self.assertEqual(self.mailer.sent, [])

    def test_ohne_login_keine_antwort(self):
        self.cookie = ""
        status, _, _ = self.request("POST", "/termin-admin/anfrage/1/antwort",
                                    form={"csrf": "x", "art": "annehmen", "betreff": "a", "text": "b"})
        self.assertEqual(status, 303)
        self.assertEqual(self.mailer.sent, [])

    def test_smtp_fehler_aendert_nichts(self):
        self.mailer.fail = True
        status, page, _ = self.reply("annehmen")
        self.assertEqual(status, 502)
        self.assertIn("konnte nicht gesendet werden", page)
        self.assertEqual(self.status_of(), "neu")
        self.assertEqual(self.count("antworten"), 0)

    def test_header_injection_im_betreff(self):
        status, _, _ = self.reply("annehmen", betreff="Hallo\r\nBcc: x@example.invalid")
        self.assertEqual(status, 400)
        self.assertEqual(self.mailer.sent, [])
        status, _, _ = self.reply("annehmen", text="  ")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
