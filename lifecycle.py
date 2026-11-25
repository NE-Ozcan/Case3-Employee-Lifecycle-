#!/usr/bin/env python3
"""
Identity Lifecycle Management - demoscript WS1 (CS3, MA-NCA), versie 2

Joiner / mover / leaver voor Innovatech Solutions:
  medewerkerstabel (SQLite)  ->  identity provider  ->  audit-log

Providers:
  lokaal  - nep-identity provider in een JSON-bestand (geen cloud nodig; oefenen en fallback)
  aws     - AWS IAM Identity Center via boto3 (identitystore + sso-admin)

Op Windows (PowerShell): gebruik `python` in plaats van `python3`.

Voorbeelden:
  python3 lifecycle.py init-db                    # demo-medewerkers aanmaken
  python3 lifecycle.py lijst                      # tabel tonen
  python3 lifecycle.py setup                      # groepen uit rollen.json aanmaken
  python3 lifecycle.py joiner 1004 --dry-run      # laten zien wat er gaat gebeuren
  python3 lifecycle.py joiner 1004                # account + groepen
  python3 lifecycle.py mover 1004 --rol it-beheerder
  python3 lifecycle.py leaver 1004                # groepen weg, account blijft (zacht)
  python3 lifecycle.py leaver 1004 --verwijder    # account ook verwijderen (hard)
  python3 lifecycle.py zet-status 1007 vertrekt   # HR meldt een vertrek (zoals de portal zou doen)
  python3 lifecycle.py sync                       # hele tabel verwerken op basis van status
  python3 lifecycle.py toon 1004                  # wat staat er in de identity provider?
  python3 lifecycle.py audit                      # laatste 20 regels audit-log (lokale tijd)
  python3 lifecycle.py audit 1004 -n 50           # alleen medewerker 1004
  python3 lifecycle.py rollen                     # de rollenmatrix uit rollen.json

Provider kiezen: --provider aws|lokaal, of de omgevingsvariabele ILM_PROVIDER.
AWS-regio: de standaard van je AWS-profiel (AWS_REGION / AWS_PROFILE).

Statussen in de tabel:  nieuw -> actief -> vertrekt -> uit_dienst

Opbouw (waar begin je?):
  main()                     argumenten -> een van de lifecycle-functies
  joiner/mover/leaver/sync   wat er per gebeurtenis moet gebeuren
  synchroniseer_groepen()    het hart: gewenste groepen vs. huidige groepen
  LokaalIdP / AwsIdP         de identity provider; een eigen provider (bijv. Keycloak)
                             is een klasse met dezelfde 9 methodes
  database, rollen, Audit    bron van waarheid, rollenmatrix, audit-log
"""

import argparse
import datetime as dt
import getpass
import json
import os
import sqlite3
import sys
import unicodedata
import uuid
from pathlib import Path

HIER = Path(__file__).resolve().parent
DB_PAD = Path(os.environ.get("ILM_DB", HIER / "medewerkers.db"))
ROLLEN_PAD = Path(os.environ.get("ILM_ROLLEN", HIER / "rollen.json"))
AUDIT_PAD = Path(os.environ.get("ILM_AUDIT", HIER / "audit.log"))
LOKAAL_IDP_PAD = Path(os.environ.get("ILM_LOKAAL_IDP", HIER / "lokaal-idp.json"))
EMAILDOMEIN = os.environ.get("ILM_DOMEIN", "innovatech.example")

STATUSSEN = ("nieuw", "actief", "vertrekt", "uit_dienst")

DEMO_MEDEWERKERS = [
    # id,  voornaam, achternaam,      afdeling,      rol,             status
    (1001, "Sane",  "de Vries",      "IT",          "it-beheerder",  "actief"),
    (1002, "Mohamed", "El Amrani",    "Development", "developer",     "actief"),
    (1003, "Lotte",  "Janssen",       "HR",          "hr-medewerker", "actief"),
    (1004, "Daan",   "Bakker",        "Development", "developer",     "nieuw"),
    (1005, "Priya",  "Ramdin",        "Sales",       "manager",       "nieuw"),
    (1006, "Tom",    "Hendriks",      "Development", "stagiair",      "nieuw"),
    (1007, "Eva",    "van den Berg",  "Finance",     "manager",       "actief"),
]


# --------------------------------------------------------------------------- hulpjes

KLEUR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _k(code, tekst):
    return f"\033[{code}m{tekst}\033[0m" if KLEUR else tekst


def ok(tekst):
    print(_k("32", "  ✔ ") + tekst)


def stap(tekst):
    print(_k("1;36", "▶ ") + _k("1", tekst))


def info(tekst):
    print("    " + tekst)


def plan(tekst):
    print(_k("33", "  ~ ") + tekst + _k("33", "  (dry-run: niet uitgevoerd)"))


def fout(tekst):
    print(_k("31", "  ✘ ") + tekst, file=sys.stderr)


def nu():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def gebruikersnaam(voornaam, achternaam):
    """'Mohamed', 'El Amrani' -> 'mohamed.elamrani' (ascii, geen spaties)."""
    ruw = f"{voornaam}.{achternaam}".lower().replace(" ", "")
    return unicodedata.normalize("NFKD", ruw).encode("ascii", "ignore").decode()


class Audit:
    """Append-only audit-log in JSON Lines: één regel per wijziging (REQ-NCA-P3-01)."""

    def __init__(self, pad, provider, dry_run):
        self.pad = pad
        self.provider = provider
        self.dry_run = dry_run
        self.uitvoerder = os.environ.get("ILM_UITVOERDER", getpass.getuser())

    def log(self, actie, medewerker_id, doel, resultaat="ok", detail=None):
        regel = {
            "tijd": nu(),
            "uitvoerder": self.uitvoerder,
            "provider": self.provider,
            "actie": actie,
            "medewerker_id": medewerker_id,
            "doel": doel,
            "resultaat": "dry-run" if self.dry_run else resultaat,
        }
        if detail:
            regel["detail"] = detail
        if self.dry_run:
            return  # dry-run verandert niets, dus ook geen audit-regel
        with open(self.pad, "a", encoding="utf-8") as f:
            f.write(json.dumps(regel, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- database

def db():
    con = sqlite3.connect(DB_PAD)
    con.row_factory = sqlite3.Row
    return con


def init_db(_args):
    if DB_PAD.exists():
        DB_PAD.unlink()
    con = db()
    con.execute(
        """CREATE TABLE employees (
               id          INTEGER PRIMARY KEY,
               voornaam    TEXT NOT NULL,
               achternaam  TEXT NOT NULL,
               email       TEXT NOT NULL UNIQUE,
               afdeling    TEXT NOT NULL,
               rol         TEXT NOT NULL,
               status      TEXT NOT NULL CHECK (status IN ('nieuw','actief','vertrekt','uit_dienst')),
               gewijzigd   TEXT NOT NULL
           )"""
    )
    for mid, vn, an, afd, rol, status in DEMO_MEDEWERKERS:
        email = f"{gebruikersnaam(vn, an)}@{EMAILDOMEIN}"
        con.execute(
            "INSERT INTO employees VALUES (?,?,?,?,?,?,?,?)",
            (mid, vn, an, email, afd, rol, status, nu()),
        )
    con.commit()
    ok(f"Database {DB_PAD.name} aangemaakt met {len(DEMO_MEDEWERKERS)} medewerkers")
    lijst(None)


def lijst(_args):
    rijen = db().execute("SELECT * FROM employees ORDER BY id").fetchall()
    kop = f"{'ID':<5} {'Naam':<22} {'Afdeling':<12} {'Rol':<14} {'Status':<10} E-mail"
    print(_k("1", kop))
    for r in rijen:
        naam = f"{r['voornaam']} {r['achternaam']}"
        kleur = {"nieuw": "33", "vertrekt": "31", "uit_dienst": "90"}.get(r["status"], "0")
        status = _k(kleur, r["status"].ljust(10))
        print(f"{r['id']:<5} {naam:<22} {r['afdeling']:<12} {r['rol']:<14} "
              f"{status} {r['email']}")


def medewerker(mid):
    r = db().execute("SELECT * FROM employees WHERE id = ?", (mid,)).fetchone()
    if r is None:
        fout(f"Medewerker {mid} staat niet in de database")
        sys.exit(2)
    return dict(r)


def zet_db(mid, dry_run, audit, **velden):
    """Wijzig velden in de medewerkerstabel. Elke wijziging komt ook in de audit-log."""
    if dry_run:
        plan(f"database: medewerker {mid} -> {velden}")
        return
    oud = medewerker(mid)
    sets = ", ".join(f"{k} = ?" for k in velden)
    con = db()
    con.execute(f"UPDATE employees SET {sets}, gewijzigd = ? WHERE id = ?",
                (*velden.values(), nu(), mid))
    con.commit()
    for veld, nieuw in velden.items():
        audit.log(f"{veld}_gewijzigd", mid, nieuw, detail={"van": oud[veld]})
    ok(f"database: medewerker {mid} -> {velden}")


# --------------------------------------------------------------------------- rollen

def laad_rollen():
    data = json.loads(ROLLEN_PAD.read_text(encoding="utf-8"))
    return data


def groepsinfo(rollen, naam):
    """rollen.json v2: per groep een object; v1: alleen een tekst."""
    g = rollen.get("groepen", {}).get(naam, {})
    return g if isinstance(g, dict) else {"omschrijving": g}


def toon_rollen(rollen):
    stap("ROLLEN  rollenmatrix uit rollen.json (rol -> groep -> rechten)")
    print(_k("1", f"    {'Rol':<15} {'Groep':<22} {'Platform (REQ-NCA-P3-10)':<52} Portal (REQ-NCA-P3-11)"))
    for rol in rollen["rollen"]:
        for g in gewenste_groepen(rol, rollen):
            info_g = groepsinfo(rollen, g)
            print(f"    {rol:<15} {g:<22} {info_g.get('platform', '?'):<52} {info_g.get('portal', '?')}")
            rol = ""


def gewenste_groepen(rol, rollen):
    if rol not in rollen["rollen"]:
        fout(f"Rol '{rol}' staat niet in {ROLLEN_PAD.name}. Bekende rollen: "
             + ", ".join(rollen["rollen"]))
        sys.exit(2)
    groepen = [rollen["basisgroep"]] + list(rollen["rollen"][rol])
    return sorted(set(groepen))


# --------------------------------------------------------------------------- providers

class LokaalIdP:
    """Een nep-identity provider in een JSON-bestand. Zelfde interface als AwsIdP."""

    naam = "lokaal"

    def __init__(self):
        if LOKAAL_IDP_PAD.exists():
            self.d = json.loads(LOKAAL_IDP_PAD.read_text(encoding="utf-8"))
        else:
            self.d = {"users": {}, "groups": {}, "memberships": []}

    def _bewaar(self):
        LOKAAL_IDP_PAD.write_text(json.dumps(self.d, indent=2, ensure_ascii=False),
                                  encoding="utf-8")

    def zoek_user(self, username):
        for uid, u in self.d["users"].items():
            if u["UserName"] == username:
                return uid
        return None

    def maak_user(self, username, voornaam, achternaam, email):
        uid = f"lokaal-u-{uuid.uuid4().hex[:8]}"
        self.d["users"][uid] = {"UserName": username, "GivenName": voornaam,
                                "FamilyName": achternaam, "Email": email}
        self._bewaar()
        return uid

    def verwijder_user(self, uid):
        self.d["users"].pop(uid, None)
        self.d["memberships"] = [m for m in self.d["memberships"] if m["UserId"] != uid]
        self._bewaar()

    def zoek_groep(self, naam):
        for gid, g in self.d["groups"].items():
            if g["DisplayName"] == naam:
                return gid
        return None

    def maak_groep(self, naam, omschrijving):
        gid = f"lokaal-g-{uuid.uuid4().hex[:8]}"
        self.d["groups"][gid] = {"DisplayName": naam, "Description": omschrijving}
        self._bewaar()
        return gid

    def groepen_van(self, uid):
        """-> {groepsnaam: membership_id}"""
        uit = {}
        for m in self.d["memberships"]:
            if m["UserId"] == uid:
                uit[self.d["groups"][m["GroupId"]]["DisplayName"]] = m["MembershipId"]
        return uit

    def voeg_toe(self, uid, gid):
        mid = f"lokaal-m-{uuid.uuid4().hex[:8]}"
        self.d["memberships"].append({"MembershipId": mid, "UserId": uid, "GroupId": gid})
        self._bewaar()

    def haal_weg(self, membership_id):
        self.d["memberships"] = [m for m in self.d["memberships"]
                                 if m["MembershipId"] != membership_id]
        self._bewaar()


class AwsFout(Exception):
    """Een AWS-fout, vertaald naar een korte melding met een tip."""


def vertaal_aws_fout(e, actie):
    naam = type(e).__name__
    code = getattr(e, "response", {}).get("Error", {}).get("Code", naam)
    bericht = getattr(e, "response", {}).get("Error", {}).get("Message", str(e))
    if "service control policy" in bericht:
        tip = ("Geweigerd door een SCP van je AWS-organisatie (bijv. het Fontys-account). "
               "Dat kun je niet zelf oplossen. Gebruik --provider lokaal of Keycloak; "
               "zie README, 'Welk AWS-account heb je nodig?'.")
    elif code in ("AccessDeniedException", "AccessDenied"):
        tip = "Je rol mist rechten voor deze actie. Zie de minimale policy in de README."
    elif code in ("ExpiredToken", "ExpiredTokenException", "UnrecognizedClientException",
                  "InvalidClientTokenId") or "Token" in naam:
        tip = "Je AWS-sessie is verlopen of ongeldig: log opnieuw in (aws sso login)."
    elif naam == "NoCredentialsError":
        tip = "Geen AWS-credentials gevonden: aws configure sso, of zet de omgevingsvariabelen."
    elif naam == "NoRegionError":
        tip = "Geen regio ingesteld: zet AWS_REGION op de regio van je Identity Center."
    elif code == "ConflictException":
        tip = ("Bestaat al (bijv. een gebruiker met hetzelfde e-mailadres maar een andere "
               "gebruikersnaam). Verwijder hem in de console of draai de reset.")
    elif naam == "EndpointConnectionError":
        tip = "Geen verbinding met AWS: check je netwerk en de regio."
    else:
        tip = "Zie de foutmelding hierboven."
    return AwsFout(f"AWS weigerde '{actie}': {code}\n      {bericht}\n    Tip: {tip}")


class AwsIdP:
    """AWS IAM Identity Center (identity store). Vereist: python -m pip install boto3, en
    AWS-credentials met rechten op identitystore:* en sso:ListInstances."""

    naam = "aws"

    def __init__(self):
        try:
            import boto3
            import botocore.exceptions as bexc
        except ImportError:
            fout("boto3 ontbreekt: python -m pip install boto3   (of gebruik --provider lokaal)")
            sys.exit(3)
        self._fouten = (bexc.ClientError, bexc.BotoCoreError)
        try:
            self.ids = boto3.client("identitystore")
            sso = boto3.client("sso-admin")
            instances = sso.list_instances().get("Instances", [])
        except self._fouten as e:
            raise vertaal_aws_fout(e, "sso:ListInstances")
        if not instances:
            fout("Geen IAM Identity Center-instance gevonden in deze regio. "
                 "Klopt AWS_REGION? Is Identity Center aangezet?")
            sys.exit(3)
        self.store = os.environ.get("ILM_IDENTITY_STORE_ID", instances[0]["IdentityStoreId"])
        info(f"Identity store: {self.store} (regio {self.ids.meta.region_name})")
        self._omhul()

    def _omhul(self):
        """Elke publieke methode: AWS-fouten -> korte melding (ResourceNotFound blijft zoals hij is)."""
        nietgevonden = self.ids.exceptions.ResourceNotFoundException
        for naam in ("zoek_user", "maak_user", "verwijder_user", "zoek_groep", "maak_groep",
                     "groepen_van", "voeg_toe", "haal_weg"):
            fn = getattr(self, naam)

            def veilig(*a, _fn=fn, _naam=naam, **k):
                try:
                    return _fn(*a, **k)
                except nietgevonden:
                    raise
                except self._fouten as e:
                    raise vertaal_aws_fout(e, _naam)
            setattr(self, naam, veilig)

    def _uniek(self, pad, waarde):
        return {"UniqueAttribute": {"AttributePath": pad, "AttributeValue": waarde}}

    def zoek_user(self, username):
        try:
            return self.ids.get_user_id(IdentityStoreId=self.store,
                                        AlternateIdentifier=self._uniek("userName", username))["UserId"]
        except self.ids.exceptions.ResourceNotFoundException:
            return None

    def maak_user(self, username, voornaam, achternaam, email):
        r = self.ids.create_user(
            IdentityStoreId=self.store,
            UserName=username,
            DisplayName=f"{voornaam} {achternaam}",
            Name={"GivenName": voornaam, "FamilyName": achternaam},
            Emails=[{"Value": email, "Type": "work", "Primary": True}],
        )
        return r["UserId"]

    def verwijder_user(self, uid):
        self.ids.delete_user(IdentityStoreId=self.store, UserId=uid)

    def zoek_groep(self, naam):
        try:
            return self.ids.get_group_id(IdentityStoreId=self.store,
                                         AlternateIdentifier=self._uniek("displayName", naam))["GroupId"]
        except self.ids.exceptions.ResourceNotFoundException:
            return None

    def maak_groep(self, naam, omschrijving):
        return self.ids.create_group(IdentityStoreId=self.store, DisplayName=naam,
                                     Description=omschrijving[:1024])["GroupId"]

    def groepen_van(self, uid):
        uit = {}
        kwargs = {"IdentityStoreId": self.store, "MemberId": {"UserId": uid}}
        while True:
            r = self.ids.list_group_memberships_for_member(**kwargs)
            for m in r.get("GroupMemberships", []):
                g = self.ids.describe_group(IdentityStoreId=self.store, GroupId=m["GroupId"])
                uit[g["DisplayName"]] = m["MembershipId"]
            if not r.get("NextToken"):
                return uit
            kwargs["NextToken"] = r["NextToken"]

    def voeg_toe(self, uid, gid):
        self.ids.create_group_membership(IdentityStoreId=self.store, GroupId=gid,
                                         MemberId={"UserId": uid})

    def haal_weg(self, membership_id):
        self.ids.delete_group_membership(IdentityStoreId=self.store,
                                         MembershipId=membership_id)


def maak_provider(naam):
    return {"lokaal": LokaalIdP, "aws": AwsIdP}[naam]()


# --------------------------------------------------------------------------- lifecycle

def zorg_groep(idp, naam, rollen, dry_run, audit):
    gid = idp.zoek_groep(naam)
    if gid:
        return gid
    if dry_run:
        plan(f"groep {naam} aanmaken")
        return f"(nieuw:{naam})"
    gid = idp.maak_groep(naam, groepsinfo(rollen, naam).get("omschrijving", ""))
    audit.log("groep_aangemaakt", None, naam)
    ok(f"groep {naam} aangemaakt")
    return gid


def synchroniseer_groepen(idp, uid, m, gewenst, rollen, dry_run, audit):
    """Breng de groepen van een gebruiker in lijn met zijn rol. Idempotent."""
    huidig = idp.groepen_van(uid) if uid and not uid.startswith("(nieuw") else {}
    erbij = [g for g in gewenst if g not in huidig]
    eraf = [g for g in huidig if g not in gewenst]
    for g in erbij:
        gid = zorg_groep(idp, g, rollen, dry_run, audit)
        if dry_run:
            plan(f"{m['_username']} toevoegen aan {g}")
            continue
        idp.voeg_toe(uid, gid)
        audit.log("groep_toegevoegd", m["id"], g, detail={"user": m["_username"]})
        ok(f"{m['_username']} toegevoegd aan {g}")
    for g in eraf:
        if dry_run:
            plan(f"{m['_username']} verwijderen uit {g}")
            continue
        idp.haal_weg(huidig[g])
        audit.log("groep_verwijderd", m["id"], g, detail={"user": m["_username"]})
        ok(f"{m['_username']} verwijderd uit {g}")
    if not erbij and not eraf:
        info(f"groepen kloppen al: {', '.join(gewenst) or '(geen)'}")


def joiner(idp, mid, dry_run, audit, rollen, reden=""):
    m = medewerker(mid)
    m["_username"] = gebruikersnaam(m["voornaam"], m["achternaam"])
    stap(f"JOINER  {m['voornaam']} {m['achternaam']} ({m['rol']}, {m['afdeling']}){reden}")
    if m["status"] in ("vertrekt", "uit_dienst"):
        fout(f"Status is '{m['status']}': geen account aanmaken voor iemand die vertrekt")
        return False
    gewenst = gewenste_groepen(m["rol"], rollen)

    uid = idp.zoek_user(m["_username"])
    if uid:
        info(f"account {m['_username']} bestaat al ({uid}), alleen groepen controleren")
    elif dry_run:
        plan(f"account {m['_username']} aanmaken ({m['email']})")
        uid = "(nieuw)"
    else:
        uid = idp.maak_user(m["_username"], m["voornaam"], m["achternaam"], m["email"])
        audit.log("account_aangemaakt", m["id"], m["_username"], detail={"user_id": uid})
        ok(f"account {m['_username']} aangemaakt (id {uid})")

    synchroniseer_groepen(idp, uid, m, gewenst, rollen, dry_run, audit)
    if m["status"] != "actief":
        zet_db(m["id"], dry_run, audit, status="actief")
    return True


def mover(idp, mid, nieuwe_rol, dry_run, audit, rollen):
    m = medewerker(mid)
    m["_username"] = gebruikersnaam(m["voornaam"], m["achternaam"])
    rol = nieuwe_rol or m["rol"]
    if rol != m["rol"]:
        stap(f"MOVER   {m['voornaam']} {m['achternaam']}: {m['rol']} -> {rol}")
    else:
        stap(f"CONTROLE {m['voornaam']} {m['achternaam']} ({rol})")
    gewenst = gewenste_groepen(rol, rollen)
    uid = idp.zoek_user(m["_username"])
    if not uid:
        fout(f"{m['_username']} heeft nog geen account: eerst joiner draaien")
        return False
    synchroniseer_groepen(idp, uid, m, gewenst, rollen, dry_run, audit)
    if rol != m["rol"]:
        zet_db(m["id"], dry_run, audit, rol=rol)
    return True


def leaver(idp, mid, verwijder, dry_run, audit, rollen):
    m = medewerker(mid)
    m["_username"] = gebruikersnaam(m["voornaam"], m["achternaam"])
    stap(f"LEAVER  {m['voornaam']} {m['achternaam']} ({'hard: account verwijderen' if verwijder else 'zacht: alle groepen weg'})")
    uid = idp.zoek_user(m["_username"])
    if not uid:
        info(f"geen account {m['_username']} gevonden: niets in te trekken")
        audit.log("geen_account", m["id"], m["_username"], detail={"bij": "leaver"})
    else:
        synchroniseer_groepen(idp, uid, m, [], rollen, dry_run, audit)
        if verwijder:
            if dry_run:
                plan(f"account {m['_username']} verwijderen")
            else:
                idp.verwijder_user(uid)
                audit.log("account_verwijderd", m["id"], m["_username"], detail={"user_id": uid})
                ok(f"account {m['_username']} verwijderd")
        kop = "Let op" if idp.naam == "aws" else "In AWS IAM Identity Center geldt"
        print(_k("33", f"    {kop}:"))
        info("- uitschakelen kan alleen in de console, er is geen API voor (wel voor verwijderen);")
        info("- een al gestarte rolsessie (permission set) blijft geldig tot hij verloopt, max. 12 uur.")
    if m["status"] != "uit_dienst":
        zet_db(m["id"], dry_run, audit, status="uit_dienst")
    return True


def sync(idp, dry_run, audit, rollen):
    """Verwerk de hele tabel: nieuw -> joiner, actief -> controle (mover), vertrekt -> leaver."""
    rijen = db().execute("SELECT id, status FROM employees ORDER BY id").fetchall()
    teller = {"joiner": 0, "controle": 0, "leaver": 0}
    for r in rijen:
        if r["status"] == "nieuw":
            joiner(idp, r["id"], dry_run, audit, rollen); teller["joiner"] += 1
        elif r["status"] == "actief":
            if not idp.zoek_user(gebruikersnaam(*_naam(r["id"]))):
                joiner(idp, r["id"], dry_run, audit, rollen,
                       reden="  [status actief, maar nog geen account]")
                teller["joiner"] += 1
            else:
                mover(idp, r["id"], None, dry_run, audit, rollen); teller["controle"] += 1
        elif r["status"] == "vertrekt":
            leaver(idp, r["id"], False, dry_run, audit, rollen); teller["leaver"] += 1
    print()
    ok(f"sync klaar: {teller['joiner']} joiners, {teller['controle']} gecontroleerd, "
       f"{teller['leaver']} leavers")


def _naam(mid):
    m = medewerker(mid)
    return m["voornaam"], m["achternaam"]


def setup(idp, dry_run, audit, rollen):
    stap("SETUP   groepen uit rollen.json aanmaken")
    alle = [rollen["basisgroep"]] + [g for gs in rollen["rollen"].values() for g in gs]
    for g in sorted(set(alle)):
        if idp.zoek_groep(g):
            info(f"groep {g} bestaat al")
        else:
            zorg_groep(idp, g, rollen, dry_run, audit)


def toon(idp, mid):
    m = medewerker(mid)
    username = gebruikersnaam(m["voornaam"], m["achternaam"])
    stap(f"TOON    {username}")
    info(f"database : rol={m['rol']}, status={m['status']}")
    uid = idp.zoek_user(username)
    if not uid:
        info(f"{idp.naam:<9}: geen account")
        return
    groepen = sorted(idp.groepen_van(uid))
    info(f"{idp.naam:<9}: account {uid}")
    info(f"groepen  : {', '.join(groepen) or '(geen)'}")
    for g in groepen:
        gi = groepsinfo(laad_rollen(), g)
        info(f"  {g:<22} platform: {gi.get('platform', '?')}; portal: {gi.get('portal', '?')}")


def toon_audit(mid, n):
    if not AUDIT_PAD.exists():
        info("nog geen audit-log")
        return
    regels = [json.loads(r) for r in AUDIT_PAD.read_text(encoding="utf-8").splitlines() if r.strip()]
    if mid is not None:
        regels = [r for r in regels if r.get("medewerker_id") == mid]
    print(_k("1", f"{'Tijd (lokaal)':<20} {'Uitvoerder':<12} {'Actie':<20} {'ID':<5} Doel"))
    for r in regels[-n:]:
        tijd = dt.datetime.fromisoformat(r["tijd"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{tijd:<20} {r['uitvoerder']:<12} {r['actie']:<20} "
              f"{str(r['medewerker_id'] or ''):<5} {r['doel']}")
    if len(regels) > n:
        info(f"({len(regels) - n} oudere regels niet getoond: gebruik -n)")


# --------------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="Identity Lifecycle Management (WS1 CS3)")
    p.add_argument("--provider", default=os.environ.get("ILM_PROVIDER", "lokaal"),
                   choices=["lokaal", "aws"])
    p.add_argument("--dry-run", action="store_true",
                   help="laat zien wat er zou gebeuren, verander niets")
    # --dry-run mag ook achter het subcommando staan
    gedeeld = argparse.ArgumentParser(add_help=False)
    gedeeld.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                         help="laat zien wat er zou gebeuren, verander niets")
    sub = p.add_subparsers(dest="cmd", required=True)
    _orig = sub.add_parser
    sub.add_parser = lambda *a, **k: _orig(*a, parents=[gedeeld], **k)
    sub.add_parser("init-db", help="demo-medewerkerstabel (opnieuw) aanmaken")
    sub.add_parser("lijst", help="medewerkerstabel tonen")
    sub.add_parser("setup", help="groepen uit rollen.json aanmaken")
    for naam in ("joiner", "toon"):
        s = sub.add_parser(naam)
        s.add_argument("id", type=int)
    s = sub.add_parser("mover")
    s.add_argument("id", type=int)
    s.add_argument("--rol", help="nieuwe rol (zonder: groepen controleren tegen huidige rol)")
    s = sub.add_parser("leaver")
    s.add_argument("id", type=int)
    s.add_argument("--verwijder", action="store_true", help="account ook verwijderen")
    s = sub.add_parser("zet-status", help="HR past de status aan (zoals de portal of het HR-systeem)")
    s.add_argument("id", type=int)
    s.add_argument("status", choices=STATUSSEN)
    sub.add_parser("sync", help="hele tabel verwerken op basis van status")
    s = sub.add_parser("audit", help="audit-log tonen (tijden in lokale tijd; in het bestand UTC)")
    s.add_argument("id", type=int, nargs="?", help="alleen deze medewerker")
    s.add_argument("-n", type=int, default=20, help="aantal regels (standaard 20)")
    sub.add_parser("rollen", help="de rollenmatrix uit rollen.json tonen")
    a = p.parse_args()

    if a.cmd == "init-db":
        return init_db(a)
    if a.cmd == "lijst":
        if not DB_PAD.exists():
            fout("Geen database gevonden. Draai eerst: python lifecycle.py init-db  (macOS/Linux: python3)")
            sys.exit(2)
        return lijst(a)
    if a.cmd == "audit":
        return toon_audit(a.id, a.n)
    if not DB_PAD.exists() and a.cmd not in ("setup", "rollen"):
        fout("Geen database gevonden. Draai eerst: python lifecycle.py init-db  (macOS/Linux: python3)")
        sys.exit(2)
    if a.cmd == "zet-status":
        medewerker(a.id)
        return zet_db(a.id, a.dry_run, Audit(AUDIT_PAD, "database", a.dry_run), status=a.status)

    rollen = laad_rollen()
    if a.cmd == "rollen":
        return toon_rollen(rollen)
    try:
        uitvoeren(a, rollen)
    except AwsFout as e:
        fout(str(e))
        sys.exit(4)


def uitvoeren(a, rollen):
    idp = maak_provider(a.provider)
    audit = Audit(AUDIT_PAD, idp.naam, a.dry_run)
    if a.dry_run:
        print(_k("33", "DRY-RUN: er wordt niets gewijzigd\n"))

    if a.cmd == "setup":
        setup(idp, a.dry_run, audit, rollen)
    elif a.cmd == "joiner":
        joiner(idp, a.id, a.dry_run, audit, rollen)
    elif a.cmd == "mover":
        mover(idp, a.id, a.rol, a.dry_run, audit, rollen)
    elif a.cmd == "leaver":
        leaver(idp, a.id, a.verwijder, a.dry_run, audit, rollen)
    elif a.cmd == "sync":
        sync(idp, a.dry_run, audit, rollen)
    elif a.cmd == "toon":
        toon(idp, a.id)


if __name__ == "__main__":
    main()
