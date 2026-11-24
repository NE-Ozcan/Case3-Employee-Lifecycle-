# Rollenmatrix: [naam referentiebedrijf]

*Werkblad WS1, laatste 10 minuten. Basis voor je IAM Implementation Report en voor `rollen.json`.*

**Spelregels**
1. Rechten hangen aan **groepen**, nooit aan personen.
2. **Least privilege:** begin met niets en voeg alleen toe wat de rol nodig heeft.
3. Twee lagen: het **platform** (cloud en cluster, REQ-NCA-P3-10) en de **applicatie** (portal of app, REQ-NCA-P3-11).
4. Gebruik je persona's uit de contextworkshop (joiner, mover, leaver).

## 1. Matrix

| Rol (uit je medewerkerstabel) | Groep(en) | Cloud (permission set / IAM-rol) | Kubernetes (namespace + rechten) | Portal / app (rol) | MFA? | Wie keurt goed? |
|---|---|---|---|---|---|---|
| *voorbeeld: developer* | *ino-alle-medewerkers, ino-developers* | *ReadOnly* | *dev: edit* | *medewerker* | *ja* | *teamlead* |
| | | | | | | |
| | | | | | | |
| | | | | | | |
| | | | | | | |

## 2. Lifecycle per persona

| Persona | Gebeurtenis | Wat moet het script doen? | Hoe snel? |
|---|---|---|---|
| Joiner | Eerste werkdag | | *bijv. vóór 08:00 op dag 1* |
| Mover | Andere afdeling of rol | | |
| Leaver | Laatste werkdag | | *bijv. binnen 1 uur na uit dienst* |

## 3. Drie vragen voor je rapport

1. Wat gebeurt er met de rechten van een **mover**: komt er alleen iets bij, of gaat er ook iets af? (Anders stapelen rechten zich op: *privilege creep*.)
2. **Zacht of hard** offboarden: wanneer schakel je uit en wanneer verwijder je? Hoe lang bewaar je gegevens (AVG)?
3. Wie mag het script draaien, en met welke rechten? Hoe bewijs je achteraf wie wat heeft gedaan?
