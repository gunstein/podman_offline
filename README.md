# MyProduct: Todo med Duende og PostgreSQL

Et lite, kjørbart Podman-eksempel med fem pods. Frontend er vanlig
HTML og JavaScript. Python-backenden håndterer innlogging hos Duende med
Authorization Code + PKCE og `private_key_jwt`. Nettleseren får en HttpOnly-cookie;
OIDC-tokenene sendes ikke til JavaScript. Hver bruker har sine egne oppgaver.

```text
Nettleser ── HTTPS :8443 ── nginx reverse proxy (egen pod)
                            ├── /             → frontend :8080 (Todo-pod)
                            ├── /auth/, /api/ → Python-backend :8000 (samme Todo-pod)
                            │                    └── Todo PostgreSQL (egen pod)
                            └── /identity/    → Duende (egen pod)
                                                 └── Identity PostgreSQL (egen pod)
```

Kun nginx publiserer en port. Alle pods bruker Podman-nettverket `myproduct`.
Det er ingen Kubernetes Services eller Ingress-controller; Podman DNS bruker
pod-navnene som står i manifestene. Todo-poden `myproduct-todo` deler nettverk
mellom frontend på port 8080 og backend på port 8000.

## Kjør lokalt, rootless

Krever Podman, OpenSSL, Python 3.6+ og PyYAML på verten. .NET og Python-appens
avhengigheter installeres bare i imagene. Første bygg trenger internett.

```sh
./scripts/build-images.sh
./scripts/generate-certificates.sh
cp config.example.yaml config.yaml
chmod 600 config.yaml
./scripts/dev.sh up
```

Legg denne linjen i vertens `/etc/hosts` manuelt:

```text
127.0.0.1 myproduct-proxy
```

Importer **kun CA-sertifikatet** `PKI/private/ca.crt` i nettleserens lokale
CA-lager, og åpne **https://myproduct-proxy:8443**. Det samme navnet løses
internt av Podman, slik at nettleseren og backenden bruker identisk OIDC issuer.
Standardoppsettet er ment for én lokal maskin. Ved bruk på andre maskiner må
DNS/navn, sertifikat, `PUBLIC_ORIGIN` og portoppsettet tilpasses samlet.

Brukerne `alice` og `bob` opprettes ved første oppstart. Passordene er generert
lokalt og ligger i henholdsvis `generated-certificates/users/alice-password`
og `bob-password`. Passordene lagres som hash i Duendes PostgreSQL-database.
Eksisterende brukerpassord endres ikke automatisk hvis kildefilene senere endres.

```sh
podman ps --all --pod
./scripts/dev.sh down
```

`down` beholder databasevolumene og Todo-sertifikatvolumet. Ny `up` importerer
filene fra `VOLUME_FILES` på nytt, men beholder eksisterende databaseinnhold.
Nettverket og navngitte volumer fjernes bare manuelt når de ikke lenger trengs.

## Manifester og sertifikater

- `manifests/10-configmap.yaml`: felles offentlig adresse via config-placeholder.
- `20-storage.yaml`: separate PVC-er for de to databasene og Duendes cookie-nøkler.
- `30-identity-postgres.yaml` og `40-todo-postgres.yaml`: hver sin PostgreSQL-pod.
- `50-identity.yaml`: Duende med privat signeringsnøkkel og sertifikat fra Secret.
- `60-todo.yaml`: frontend og Python-backend i samme pod. Bare backenden monterer
  Todo-klientsertifikat/nøkkel fra PVC og databasepassordet fra Secret.
- `80-proxy.yaml`: nginx reverse proxy med HTTPS-sertifikat fra Secret.

`SECRET_FILES` genererer Secret-dokumentene. `VOLUME_FILES.todo-signing`
genererer importarkivet og PVC-en som monteres read-only i Python-backenden.
Den inneholder `todo-client.key`, `todo-client.crt`, CA-sertifikatet og en egen
cookie-signeringhemmelighet. Duende får bare klientens **offentlige** sertifikat
og verifiserer klientens signerte JWT ved token-endepunktet. Duendes egen
signeringsnøkkel brukes til OIDC-tokenene. TLS bruker et tredje nøkkelpar.
Se [PKI](PKI/README.md).

Dette er et lite demooppsett: Duendes brukere ligger i PostgreSQL, mens klient- og
scope-konfigurasjon er i kode og kortlivede OAuth-grants ligger i minnet.
Pågående innlogging må derfor startes på nytt etter restart av Duende.
Utlogging avslutter Todo-sesjonen; neste innlogging ber alltid om passord på nytt.
Databasene bruker én rolle per app, uten egne migreringsroller. Automatisk
skjemaoppretting er kun for dette enkle eksempelet. Duende krever en passende
[lisens for produksjon](https://docs.duendesoftware.com/identityserver/overview/licensing/).

## Kontroll av hele flyten

Med appens avhengigheter i et lokalt testmiljø:

```sh
python3 -m venv .venv-app
.venv-app/bin/pip install -r apps/todo-backend/requirements.txt
.venv-app/bin/python scripts/smoke-test.py
```

Denne testen bruker ekte HTTPS og Duende-innlogging med begge brukerne, verifiserer
CRUD, tilgangsskille mellom brukere, CSRF-beskyttelse og lokal utlogging. Den
verifiserer CA/vertsnavn og trenger ingen endring i `/etc/hosts`. Dette er en
HTTP-integrasjonstest; frontend-JavaScript må også prøves i en nettleser.
De isolerte renderer-/bundle-testene kjøres med `python3 -m unittest discover -s tests`.
Se også de små [Podman-eksemplene](examples/README.md).

Verifisert 2026-10-12 med ekte rootless Podman 5.7.0: alle fem pods starter,
og hele HTTP-integrasjonstesten passerer gjennom nginx. De 60 enhetstestene
passerer med både PyYAML 5.4.1 og 6.0.3. Ruff, Pyright og kontroll av Python
3.6-kompatibilitet for deploy/bundle/testene er rene. Rootful Quadlet og reboot
er ikke kjørt.

## Offline-bundle og rootful Quadlet

Manifestene er eneste kilde for images. Byggingen leser `containers` og
`initContainers` fra alle `manifests/*.yaml`, fjerner duplikater og sorterer navnene.
Images må allerede være hentet med `podman pull` eller bygget med `podman build`
på byggemaskinen, med nøyaktig samme fulle navn og tagg som i manifestet.
`./scripts/build-images.sh` gjør dette for demoen.

Bruk helst fulle originalnavn, for eksempel `registry.firma.no/team/app:1.2.3`,
og `imagePullPolicy: Never`. Også `localhost/myapp:1.0.0` og navn med registry-port
godtas. Korte navn som `postgres:16` og `team/app:1` avvises. Placeholders i
image-navn støttes ikke ved bygging, og manifestene må inneholde minst ett image.
For en ny image-versjon endrer du taggen i manifestet; ingen separat image-liste
må oppdateres. Det nye imaget må være tilgjengelig lokalt før bundle-byggingen.

Kjør `./build-bundle.sh` med Podman 4.4 eller nyere. `bundle.py` bruker
`podman save -m` med standardformatet docker-archive og lager
`dist/myproduct-0.1.0-offline.tar.gz` med manifests, deploy, scripts, Quadlet og
checksums. `images/images.tar` er ett arkiv med alle imagene og deres fulle navn
og tagger. `images/images.txt` lister navnene, ett per linje. Begge filene inngår
i checksums. Private nøkler, lokal config og PKI blir ikke pakket med.

På målmaskinen: verifiser checksums, generer lokale testsertifikater med
`./scripts/generate-certificates.sh`, kopier og tilpass `config.example.yaml`.
Produksjonssertifikater kan også leveres til stiene i config. Opprett nettverket
én gang, og installer deretter:

```sh
sudo podman network create myproduct
sudo ./deploy install
```

`install` sjekker først root, rendrer YAML og kjører
`podman load -i images/images.tar`. Deretter kontrolleres hvert image fra den
rendrede YAML-en med `podman image exists`. Manglende arkiv eller image stopper
installasjonen før Quadlet-filene skrives og tjenesten restartes. Ved vellykket
kontroll installeres `/etc/containers/systemd/myproduct.*` og Quadlet-tjenesten
startes. Filarkiver plasseres i `/var/lib/myproduct/files`.
`prepare` rendrer som før, uten å laste eller kontrollere images hos Podman.
Dette demonstrasjonsoppsettet er ikke produksjonsverifisert; rootful/systemd/reboot
kontrolleres manuelt etter [VM-sjekklisten](examples/VM-CHECKLIST.md).
