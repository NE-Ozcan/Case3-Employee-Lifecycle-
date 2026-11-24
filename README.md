# WS1 Identity Lifecycle Management: demo-kit

*CS3 MA-NCA, workshop 1 (woensdag 25 november 2026). Versie 2.1, 24 november 2026: bijgewerkt na testrun 1 (zie `WS1-CHANGELOG.md`).*

Eén script dat een medewerker uit de database haalt, een account aanmaakt in de identity provider, de juiste groepen koppelt en alles vastlegt in een audit-log. En hetzelfde in omgekeerde richting als iemand vertrekt.

```
medewerkers.db (HR-tabel)  ──►  lifecycle.py  ──►  identity provider (lokaal | AWS IAM Identity Center | jouw Keycloak)
        ▲                          │
        └── status bijwerken ◄─────┴──►  audit.log (wie, wat, wanneer)
```

**Requirements.** In deze kit verwijzen we naar requirement-ID's uit `Case study 3.docx`:

| ID | Wat het vraagt |
|---|---|
| REQ-NCA-P3-01 | Geautomatiseerd én auditeerbaar provisionen van accounts, toegang en applicaties |
| REQ-NCA-P3-06 | De oplossing volgt Zero Trust-principes (hier: identiteit als basis) |
| REQ-NCA-P3-10 | RBAC voor het beheer van platformresources (cloud, cluster) |
| REQ-NCA-P3-11 | RBAC voor eindgebruikers (portal of app), via een centrale identity provider |

## Inhoud

| Bestand | Wat |
|---|---|
| `lifecycle.py` | Joiner, mover, leaver en sync. Alleen standaard-Python, plus `boto3` voor AWS |
| `rollen.json` | De rollenmatrix als code: rol → groepen, en per groep de rechten op platform en portal |
| `rollenmatrix-template.md` | Werkblad voor de laatste 10 minuten van de workshop |
| `medewerkers.db` | Ontstaat met `init-db`: de tabel uit de case (ID, naam, e-mail, afdeling, status, rol) |
| `audit.log` | Ontstaat bij de eerste wijziging. JSON Lines, één regel per wijziging, tijden in UTC |

## Snel starten (zonder cloud)

Standaard draait alles tegen de **lokale provider**: een nep-identity provider in `lokaal-idp.json`. Zo oefen je de logica zonder account. Open `lokaal-idp.json` in VS Code om te zien wat er verandert.

**Windows (PowerShell):**

```powershell
python lifecycle.py init-db
python lifecycle.py setup
python lifecycle.py joiner 1004 --dry-run
python lifecycle.py joiner 1004
python lifecycle.py toon 1004
python lifecycle.py leaver 1004
python lifecycle.py audit
```

**macOS / Linux (bash):** hetzelfde, met `python3` in plaats van `python`.

Op Windows geeft `python3` de melding *"Python is niet gevonden; uitvoeren zonder argumenten om te installeren vanaf de Microsoft Store"*. Dat is een snelkoppeling van Windows: gebruik `python`.

## Commando's

| Commando | Wat het doet |
|---|---|
| `init-db` | Medewerkerstabel (opnieuw) aanmaken met demodata en tonen. **Wist de bestaande tabel** |
| `lijst` | Tabel tonen |
| `rollen` | De rollenmatrix uit `rollen.json` tonen: rol → groep → rechten |
| `setup` | Alle groepen uit `rollen.json` aanmaken (idempotent) |
| `joiner <id>` | Account aanmaken als het nog niet bestaat, groepen gelijkzetten met de rol, status → `actief` |
| `mover <id> --rol <rol>` | Groepen aanpassen aan de nieuwe rol: wat erbij moet erbij, wat weg moet eraf |
| `leaver <id>` | Alle groepen weg (zacht), status → `uit_dienst`. Met `--verwijder` ook het account weg (hard) |
| `zet-status <id> <status>` | Doet wat HR of de portal zou doen: `nieuw`, `actief`, `vertrekt`, `uit_dienst` |
| `sync` | Hele tabel verwerken: `nieuw` → joiner, `actief` → controle (of joiner als er nog geen account is), `vertrekt` → leaver |
| `toon <id>` | Database, account, groepen en de rechten per groep |
| `audit [id] [-n 50]` | Audit-log tonen (standaard laatste 20 regels), eventueel voor één medewerker. Tijden in lokale tijd |

Elke wijzigende opdracht kan met `--dry-run`. Het script is **idempotent**: twee keer `joiner` maakt geen tweede account, en `sync` kun je elke nacht draaien. Elke wijziging, ook een statuswijziging in de database, komt in `audit.log`.

**Waarom UTC in de log?** Logs uit verschillende systemen en tijdzones moeten op één tijdlijn passen. Het bestand bewaart UTC; het commando `audit` toont lokale tijd.

## Zo zit `lifecycle.py` in elkaar

Waar begin je in ± 700 regels?

```
main()  ──►  uitvoeren()
               │
               ├── joiner()  mover()  leaver()  sync()      wat er per gebeurtenis moet gebeuren
               │        │
               │        └──► synchroniseer_groepen()       het hart: gewenste vs. huidige groepen
               │                      │
               │                      ▼
               │             identity provider-klasse       LokaalIdP | AwsIdP | jouw KeycloakIdP (| IamIdP)
               │
               ├── database: medewerker(), zet_db()         bron van waarheid (SQLite in de demo)
               ├── rollen:   gewenste_groepen()             rollen.json
               └── Audit.log()                              audit.log
```

Een uitgebreidere versie van dit plaatje, en een situatiebeeld van de hele workshop, staan als bijlage op slide 10 en 11 van de presentatie (`opbouw-lifecycle-py.png`, `situatiebeeld.png`).

**Een eigen identity provider toevoegen** (bijvoorbeeld Keycloak): schrijf een klasse met deze methodes, en voeg hem toe aan `maak_provider()` en aan `--provider`.

| Methode | Doet | Keycloak (`kcadm.sh` of Admin REST API) |
|---|---|---|
| `zoek_user(username)` | user-id of `None` | `get users -q username=...` |
| `maak_user(username, voornaam, achternaam, email)` | user-id | `create users -s username=... -s enabled=true` |
| `verwijder_user(uid)` | | `delete users/<id>` (of `update users/<id> -s enabled=false`) |
| `zoek_groep(naam)` | group-id of `None` | `get groups -q search=...` |
| `maak_groep(naam, omschrijving)` | group-id | `create groups -s name=...` |
| `groepen_van(uid)` | `{groepsnaam: lidmaatschap-id}` | `get users/<id>/groups` (gebruik het group-id als lidmaatschap-id) |
| `voeg_toe(uid, gid)` | | `update users/<id>/groups/<gid> -n` |
| `haal_weg(lidmaatschap_id)` | | `delete users/<id>/groups/<gid>` |
| `naam` (attribuut) | `"keycloak"` | |

## Welk platform voor de identity provider?

| Route | Voor wie | Status |
|---|---|---|
| **Lokaal** (`--provider lokaal`) | Demo in de workshop, oefenen, fallback | Getest op Windows 11 / Python 3.10. macOS nog niet getest |
| **Keycloak** (container, op k3s of op EduCloud) | Studenten: de route voor je deliverable, tenzij je account Identity Center toelaat | Bouw je zelf: klasse `KeycloakIdP`, zie hierboven. Keycloak kan een gebruiker wél via de API uitschakelen |
| **AWS IAM Identity Center** (`--provider aws`) | Alleen met een geschikt AWS-account (zie hieronder) | Script getest tegen een nagebootste AWS-API, nog niet tegen echte AWS |
| **Gewone AWS IAM** (users en groepen) | Mogelijke AWS-route binnen de Fontys-accounts | Werkt in het docentaccount (testrun 1, #20); nog geen `IamIdP`-klasse in de kit. Kanttekening: IAM-users voor medewerkers zijn geen best practice (in productie: federatie met tijdelijke credentials) |

### Welk AWS-account heb je nodig?

Uit testrun 1 (24 november 2026):

- **Fontys-account (SSO-rollen `fhictisb_IsbUsersPS` / `fhictisb_IsbManagersPS`): werkt niet.** Een service control policy (SCP) van de Fontys-organisatie verbiedt `sso:*`; `aws sso-admin list-instances` geeft *"explicit deny in a service control policy"*. Dat kun je niet zelf oplossen. Het script meldt dit nu met een korte tip.
- **Nieuw AWS-account op het Free plan: werkt niet zonder onomkeerbare stappen.** Identity Center vraagt eerst een upgrade naar het Paid plan en *Activate advanced features*. Beide zijn volgens AWS niet terug te draaien.
- **Nieuw account: reken op verificatietijd.** CloudShell gaf *"Your account verification is in progress. This may take up to two days for new accounts."* Maak een account dus minstens 2–3 dagen vooraf aan.
- **Gewone IAM werkt wél in het Fontys-account.** In testrun 1 lukten `create-group`, `create-user`, `add-user-to-group` en `attach-group-policy` (ReadOnlyAccess) zonder fout; de SCP blokkeert alleen Identity Center. Een eigen `IamIdP`-klasse (zelfde 9 methodes) is dus een mogelijke AWS-route. IAM kan een gebruiker wél via de API uitschakelen (`delete-login-profile`, access keys deactiveren). Inloggen als IAM-user is nog niet getest, en of studentaccounts dezelfde rechten hebben ook niet.
- **Wel geschikt:** een bestaand eigen account op het Paid plan dat niet onder een organisatie met zo'n SCP valt. Check vooraf met `aws sso-admin list-instances --region <regio>`: een lege lijst of een instance is goed, een *AccessDenied* niet.

### Eenmalige setup Identity Center (± 10 minuten, alleen met een geschikt account)

1. **Identity Center aanzetten als organization instance.** Console → IAM Identity Center → *Enable*. In een standalone account kies je *Enable IAM Identity Center with AWS Organizations*. Niet de account instance: die mist toegang tot AWS-accounts via permission sets.
2. **Onthoud de regio** (bijvoorbeeld `eu-central-1`). Het script moet in dezelfde regio draaien.
3. **E-mail-OTP aanzetten:** *Settings → Authentication → Standard authentication → Configure → Send email OTP*. Gebruikers die via de API zijn aangemaakt hebben geen wachtwoord. Let op: het demodomein `innovatech.example` bestaat niet. Wil je echt inloggen als demogebruiker, zet dan `ILM_DOMEIN` op een domein waar jij de mail ontvangt, vóór `init-db`.
4. **Groepen aanmaken:** `python lifecycle.py --provider aws setup`.
5. **Permission sets koppelen aan groepen** (REQ-NCA-P3-10). *Permission sets → Create*:
   - *Predefined* → `ReadOnlyAccess` → toewijzen aan groep `ino-developers`.
   - *Custom* → naam `PlatformAdmin`, AWS managed policy `AdministratorAccess`, *session duration* 1 uur → toewijzen aan `ino-platform-admins`.

   Toewijzen: *AWS accounts* → vink je account aan → *Assign users or groups* → tab *Groups* → groep → permission set.

### Script draaien tegen AWS

**PowerShell:**

```powershell
python -m pip install boto3
aws configure sso                 # of access keys
$env:AWS_REGION = "eu-central-1"
$env:ILM_PROVIDER = "aws"
python lifecycle.py setup
```

**bash:**

```bash
python3 -m pip install boto3
aws configure sso
export AWS_REGION=eu-central-1 ILM_PROVIDER=aws
python3 lifecycle.py setup
```

Gebruik `python -m pip`, niet los `pip`: op Windows hoort `pip` soms bij een andere Python (bijvoorbeeld die van de AWS CLI).

Het script zoekt de identity store zelf op via `sso-admin list-instances`. Heb je er meer dan één, zet dan `ILM_IDENTITY_STORE_ID=d-xxxxxxxxxx`.

**Minimale rechten** voor wie het script draait (least privilege, ook voor automatisering):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "sso:ListInstances",
      "identitystore:GetUserId", "identitystore:CreateUser", "identitystore:DeleteUser",
      "identitystore:GetGroupId", "identitystore:CreateGroup", "identitystore:DescribeGroup",
      "identitystore:ListGroupMembershipsForMember",
      "identitystore:CreateGroupMembership", "identitystore:DeleteGroupMembership"
    ],
    "Resource": "*"
  }]
}
```

### Wat je moet weten over de leaver (voor je IAM-rapport)

- **Identity Center heeft geen API om een gebruiker uit te schakelen.** Wel `DeleteUser`. *Disable user access* kan alleen in de console. Het script trekt daarom alle groepen in (zacht) of verwijdert het account (hard).
- **Lopende rolsessies lopen door.** Na uitschakelen of verwijderen kan de gebruiker niet meer inloggen en lopen applicatiesessies binnen 30 minuten af. Een al gestarte sessie met een permission set blijft geldig tot hij verloopt (maximaal 12 uur). Houd de sessieduur van gevoelige permission sets kort.
- Bronnen: [Disable user access](https://docs.aws.amazon.com/singlesignon/latest/userguide/disableuser.html), [Authentication sessions](https://docs.aws.amazon.com/singlesignon/latest/userguide/authconcept.html), [Identity Store API-acties](https://docs.aws.amazon.com/singlesignon/latest/IdentityStoreAPIReference/API_Operations.html), [Email OTP voor API-gebruikers](https://docs.aws.amazon.com/singlesignon/latest/userguide/userswithoutpwd.html), [Organization en account instances](https://docs.aws.amazon.com/singlesignon/latest/userguide/identity-center-instances.html).

## Ontwerpvragen voor je IAM-rapport

- **Twee rollen tegelijk?** Het demomodel kent één `rol` per medewerker. Opties: een samengestelde rol in `rollen.json` (bijv. `developer-beheer`), meerdere rollen via een koppeltabel (de groepen worden dan de vereniging van alle rollen), of extra toegang via een aanvraag met een einddatum. Let op scheiding van functies: wie aanvragen goedkeurt, mag ze niet zelf indienen.
- **Een GUI voor HR / P&O?** Dat is je self-service portal. P&O wijzigt via de portal alleen de bron van waarheid (de database). Een aparte sync-job (bijv. een Kubernetes CronJob) met de credentials van de identity provider doet de rest. Zo krijgt de portal zelf geen rechten in de identity provider.
- **Bewaartermijn en AVG.** De audit-log bevat medewerker-ID en gebruikersnaam, geen privégegevens. Leg vast hoe lang je hem bewaart, wie hem mag lezen en waarom. In productie hoort hij in centrale, onveranderbare opslag (bijv. de Elastic-stack uit CS2).

## Database bekijken (optioneel)

Voor de demo volstaat `lijst`. Wil je de tabel grafisch zien, of straks je eigen database uit fase 1: [Beekeeper Studio Community](https://www.beekeeperstudio.io/) (SQLite, MySQL, PostgreSQL) of de VS Code-extensie *SQLite Viewer*.

## Van demo naar jouw deliverable

Dit script is een **vertrekpunt, geen inleverbaar product**. De kit zelf telt niet als bewijs voor je portfolio: alleen wat jij eraan toevoegt.

### Stap 1: zet de kit ongewijzigd als eerste commit in Git

```bash
git add .
git commit -m "Kit WS1 v2.1 (ongewijzigd)"
git tag kit-v2.1
```

Alles na deze tag is jouw werk. Laat in je portfolio zien wat je hebt toegevoegd, bijvoorbeeld met `git diff kit-v2.1 --stat` en je commitgeschiedenis. Zo ziet je beoordelaar in één oogopslag wat van jou is.

### Stap 2: wat telt als bewijs voor leeruitkomst 3 (Enhanced Automation)

Leeruitkomst 3 vraagt dat je na methodisch onderzoek de requirements analyseert en de uitrol van infrastructuur, applicaties en bedrijfsprocessen orkestreert met code, tooling en versiebeheer.

| Bewijs | Waarom het telt | Hoort in deliverable |
|---|---|---|
| **Onderbouwde keuze van je identity provider** (Keycloak, IAM, Cognito …): criteria, bronnen, een kleine proef | Methodisch onderzoek vóór de keuze | IAM Implementation Report |
| **Een eigen provider-klasse** (`KeycloakIdP`, of `IamIdP` na overleg) met dezelfde 9 methodes | Eigen code tegen een echte identity provider | Onboarding/Offboarding Automation Scripts, Configured Cloud Identity Provider |
| **Koppeling met je eigen database** uit fase 1, in plaats van SQLite | Requirements vertaald naar een werkende integratie | Automation Scripts |
| **Uitrol als container**, bijvoorbeeld een Kubernetes CronJob of een trigger vanuit de portal, via IaC of CI | Het orkestreren van een bedrijfsproces | Automation Scripts, Updated Git Repository |
| **Geautomatiseerde tests in je pipeline**: joiner, mover, leaver, en "tweede keer draaien verandert niets" | Tooling en kwaliteit, aantoonbaar per commit | Test Plan & Results |
| **Secrets buiten Git**: credentials via een Kubernetes Secret, SSM Parameter Store of een vault | Professioneel versiebeheer | Updated Git Repository |
| **Applicatietoegang** (REQ-NCA-P3-11): de groep bepaalt de rol in je portal via OIDC of SAML | Integratie over de lagen heen | IAM Implementation Report |

**Telt niet:** de kit zelf, alleen de rollen in `rollen.json` aanpassen, of de demo opnieuw draaien.
