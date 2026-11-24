# Changelog WS1 Identity Lifecycle Management

## Versie 2.1: 24 november 2026, 15:15

| Wat | Wijziging |
|---|---|
| Testlog #20 | Gewone AWS IAM (users, groepen, policy aan groep) werkt wél in het Fontys-account. Opgenomen in de README (routetabel, *Welk AWS-account heb je nodig?*, checklist) en als verwachte vraag in het draaiboek. **Nog geen `IamIdP`-klasse gebouwd.** |
| Draaiboek | Canvas-aankondiging vervangen door de nieuwe tekst (zonder Identity Center, met `python --version`-check) |
| Testrun-briefing | Statusregel bovenaan: uitgevoerd, verwerkt in v2/v2.1 |
| Diagrammen | Nieuw: `situatiebeeld` (bron → script → identity provider met status per route → rechten) en `opbouw-lifecycle-py` (commando's, lifecycle, `synchroniseer_groepen()`, gegevens en log, provider-klassen incl. `AwsFout`, `KeycloakIdP`, `IamIdP`). Als PNG, PDF en HTML-bron |
| Presentatie | Slide 10 (opbouw van het script) vervangen door het nieuwe diagram; slide 11 (situatiebeeld) toegevoegd als bijlage. Draaiboek en README verwijzen ernaar |
| Leeruitkomst 3 | De kit telt niet als bewijs. Studenten zetten hem ongewijzigd als eerste commit (tag `kit-v2.1`); alleen wat daarna komt telt. README: sectie *Van demo naar jouw deliverable* met een tabel "wat telt als bewijs" per deliverable. Slide 9 en draaiboek (nieuwe sectie *Bewijs voor leeruitkomst 3*, verwachte vraag, afsluiting) aangepast. `.gitignore` toegevoegd aan de kit |
| Pakket | Alle WS1-documenten gebundeld in `WS1-Identity-Lifecycle-v2.1.zip` |

## Versie 2: 24 november 2026, na testrun 1

Bron: `claude/WS1-Testlog-testrun-1.md`. Nummers (#) verwijzen naar de bevindingen in die testlog.

**Besluit voor de workshop van 25 november:** de demo draait op `--provider lokaal`. AWS IAM Identity Center wordt uitgelegd, niet getoond. Reden: een SCP blokkeert het in het Fontys-account (#4), en een nieuw Free-plan-account vraagt een onomkeerbare upgrade (#10, #11).

### `lifecycle.py`

| # | Wijziging |
|---|---|
| 5 | AWS-fouten (geweigerde actie, SCP, verlopen sessie, geen credentials, geen regio, conflict, geen verbinding) geven nu een korte melding met een tip in plaats van een traceback. Exitcode 4 |
| 6 | Elke databasewijziging (status, rol) komt in `audit.log` als `status_gewijzigd` / `rol_gewijzigd` met de oude waarde, ook via `zet-status`. Een leaver zonder account logt `geen_account` |
| 7 | `audit [id] [-n N]`: filter op medewerker, standaard 20 regels, melding als er oudere regels zijn |
| 8 | `sync` noemt een joiner voor een actieve medewerker zonder account: *[status actief, maar nog geen account]* |
| 9 | `audit` toont lokale tijd; het bestand blijft UTC |
| 13 | De leaver toont ook lokaal de twee AWS-regels, als *In AWS IAM Identity Center geldt* |
| 16 | Nieuw commando `rollen` (de rollenmatrix); `toon` laat per groep de platform- en portalrechten zien |
| 1 | Meldingen noemen `python -m pip install boto3` |
| | Docstring: Windows-tip en een korte opbouw van het script |

### `rollen.json`

| # | Wijziging |
|---|---|
| 16 | Per groep de velden `omschrijving`, `platform`, `portal`. Gelijk aan slide 4 en het voorbeeldantwoord in het draaiboek. `PlatformAdmin` (sessie 1 uur) overal dezelfde naam. Het script leest ook nog het oude formaat |

### README

| # | Wijziging |
|---|---|
| 3 | PowerShell naast bash; uitleg over de `python3`-melding op Windows |
| 1 | `python -m pip install boto3` |
| 2, 4, 10, 11 | Nieuwe sectie *Welk AWS-account heb je nodig?* en een routetabel lokaal / Keycloak / Identity Center |
| 15 | Tabel met de vier requirements, één schrijfwijze (REQ-NCA-P3-xx) |
| 16 | Stap 5: custom permission set `PlatformAdmin` (AdministratorAccess, sessie 1 uur) in plaats van alleen `AdministratorAccess` |
| 17 | Optionele databaseviewer (Beekeeper Studio, SQLite Viewer) |
| open vragen | Structuurplaat van het script; tabel met de 9 provider-methodes en de Keycloak-commando's; ontwerpvragen (twee rollen, GUI voor P&O, AVG); waarschuwing over het demodomein `innovatech.example` en `ILM_DOMEIN` |

### Draaiboek (Claude Doc)

| # | Wijziging |
|---|---|
| 14 | Overzicht, voorbereiding en als-het-misgaat herschreven voor de lokale demo; `lokaal-idp.json` in VS Code vervangt de console |
| 3, 12 | Spiekbriefje in PowerShell, inclusief de geteste reset; verwachte uitkomst van `sync` |
| 15 | Requirements-tabel met omschrijving en waar ze in WS1 terugkomen |
| 19 | Demo in twee blokken, gelijk aan de slides; tijden uit de test, meer ruimte bij de leaver |
| 16 | Voorbeeldantwoord rollenmatrix gelijk aan `rollen.json` en slide 4 |
| open vragen | Verwachte vragen: waarom geen live Identity Center, welke IdP voor studenten, Keycloak-klasse, twee rollen, GUI voor HR, UTC |
| 14 | Canvas-tekst neutraal ("in de identity provider") en de Windows-tip |

### Presentatie

| # | Wijziging |
|---|---|
| 3, 18 | Slide 6 en 7: `python`; slide 6 wijst op `lokaal-idp.json`; slide 7: de AWS-kaarten staan onder *Zo werkt het in AWS Identity Center* |
| 19 | Slide 7 heet *Leaver, audit en sync*, gelijk aan het draaiboek; `audit 1004` in de demo |
| 15, 16 | Slide 4: zelfde matrix als `rollen.json` (met stagiair), REQ-NCA-P3-10/11 voluit; slide 5: REQ-NCA-P3-01 |
| 18 | Slide 9: identity provider = Keycloak, of Identity Center als je account het toelaat |
| open vragen | Nieuwe slide 10 (bijlage): opbouw van `lifecycle.py` |

### Nog open (niet in versie 2)

- **Welke AWS-accounts hebben studenten?** Waarschijnlijk hetzelfde type als het docentaccount (SCP blokkeert `sso:*`). Verifiëren met één studentaccount of bij Fontys cloudbeheer. Dan is het besluit in `CS3-Workshopplanning-en-handouts-briefing.md` §2a (Identity Center als IdP op AWS) niet uitvoerbaar en wordt Keycloak de hoofdroute.
- Uitzondering op SCP `p-rh4p7uky` voor een docentaccount; laat de SCP Cognito toe?
- `IamIdP`-klasse voor gewone AWS IAM (#20): AWS-demo zonder Identity Center. Nog te testen: inloggen als IAM-user, rechten van studentaccounts.
- Niet getest: macOS, slides op een beamer, de AWS-route als geheel, de minimale IAM-policy, `KeycloakIdP` (bestaat nog niet; staat als huiswerk in de kit).

## Versie 1: 24 november 2026

Eerste versie: script, `rollen.json`, README, werkblad, draaiboek en presentatie (9 slides).
