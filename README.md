# MyProduct: Todo med Duende og PostgreSQL

Et lite, kjørbart Podman-eksempel med seks pods. Frontend er vanlig
HTML og JavaScript. Python-backenden håndterer innlogging hos Duende med
Authorization Code + PKCE og `private_key_jwt`. Nettleseren får en HttpOnly-cookie;
OIDC-tokenene sendes ikke til JavaScript. Hver bruker har sine egne oppgaver.

```text
Nettleser ── HTTPS :8443 ── nginx reverse proxy (egen pod)
                            ├── /             → frontend :8080 (Todo-pod)
                            ├── /auth/, /api/ → Python-backend :8000 (samme Todo-pod)
                            │                    └── Todo PostgreSQL (egen pod)
                            ├── /help/        → hjelpesider (egen pod)
                            └── /identity/    → Duende (egen pod)
                                                 └── Identity PostgreSQL (egen pod)
```

Kun nginx publiserer en port. Alle pods bruker Podman-nettverket `myproduct`.
Det er ingen Kubernetes Services eller Ingress-controller; Podman DNS bruker
pod-navnene som står i manifestene. Todo-poden `myproduct-todo` deler nettverk
mellom frontend på port 8080 og backend på port 8000.

Todo har lenker til hjelpesidene på **/help/**. Help-appen kjører i egen pod
(`myproduct-help`) og serverer vanlig HTML/CSS gjennom samme HTTPS-proxy.
Hjelpen er tilgjengelig uten innlogging og bruker ingen database. Sidene ligger
i `apps/help/`; bygg help-imaget på nytt når innholdet endres.

## Kjør lokalt, rootless

Krever Podman, OpenSSL, Python 3.6+ og PyYAML på verten. .NET og Python-appens
avhengigheter installeres bare i imagene. Første bygg trenger internett.

```sh
./dev/build-images.sh
./scripts/generate-certificates.sh
cp config.example.yaml config.yaml
chmod 600 config.yaml
./dev/dev.sh up
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
./dev/dev.sh down
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
- `70-help.yaml`: statisk help-app med innlogging, oppgaver og feilsøking.
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
Databasene bruker én rolle per app, uten egne migreringsroller. PostgreSQL-imagets
`POSTGRES_USER` oppretter en superbruker i appens separate klynge; appene lager
og eier tabellene selv. Automatisk skjemaoppretting er kun for dette enkle eksempelet. Duende krever en passende
[lisens for produksjon](https://docs.duendesoftware.com/identityserver/overview/licensing/).

## Kontroll av hele flyten

Med appens avhengigheter i et lokalt testmiljø:

```sh
python3 -m venv .venv-app
.venv-app/bin/pip install -r apps/todo-backend/requirements.txt
.venv-app/bin/python dev/smoke-test.py
```

Denne testen bruker ekte HTTPS og Duende-innlogging med begge brukerne, verifiserer
CRUD, tilgangsskille mellom brukere, CSRF-beskyttelse og lokal utlogging.
Den følger også hjelpelenkene fra Todo og kontrollerer sidene, navigasjonen,
stilarket, /help-redirect og 404 for ukjente hjelpesider. Den
verifiserer CA/vertsnavn og trenger ingen endring i `/etc/hosts`. Dette er en
HTTP-integrasjonstest; frontend-JavaScript må også prøves i en nettleser.
De isolerte renderer-/bundle-testene kjøres med `python3 -m unittest discover -s tests`.
Se også de små [Podman-eksemplene](examples/README.md).

Verifisert 2026-10-12 med ekte rootless Podman 5.7.0: alle seks pods starter,
og hele HTTP-integrasjonstesten passerer gjennom nginx. De 84 enhetstestene
passerer med både PyYAML 5.4.1 og 6.0.3. Ruff, Pyright og kontroll av Python
3.6-kompatibilitet for deploy/bundle/testene var rene ved denne dev-kjøringen.
Dette dokumenterer ikke prod-Quadlet eller reboot.

## Helsesjekker

Alle sju appcontainere har én exec-basert `livenessProbe`, håndhevet av Podman:

| Container | Lokal kontroll |
| --- | --- |
| identity-postgres-db / todo-postgres-db | `pg_isready` med samme bruker og database som PostgreSQL-miljøvariablene. |
| identity-app | Bash `/dev/tcp` krever HTTP 200 fra `127.0.0.1:8080/identity/health`. |
| todo-backend | Python `urllib.request` krever HTTP 204 fra `127.0.0.1:8000/livez`, uten database eller innlogging. |
| todo-frontend / help-web | BusyBox `wget` mot egen `127.0.0.1:8080/`. |
| proxy-nginx | BusyBox `wget` mot egen HTTPS `/livez`, med `HTTPS_PORT` fra miljøet og uten sertifikatkontroll. |

Liveness avhenger aldri av andre pods. `/api/health` sjekker fortsatt databasen
for kontroll/e2e; den brukes ikke som probe. Proxyens `/livez` returnerer 204
lokalt og ruter aldri til backendens `/livez`.

`initialDelaySeconds: 90` dekker oppstarten, inkludert appenes opptil 60 sekunders
venting på databasen. Podman kjører ingen sjekk i denne perioden; status er
`starting` i inntil 90 sekunder etter hver start, og blir `healthy` etter neste
vellykkede sjekk. Proben kjøres hvert 30. sekund med timeout 5 sekunder; tre
feil på rad gir `unhealthy` og automatisk restart med `restartPolicy: Always`.
Ingen readiness-probe eller HEALTHCHECK i Containerfile brukes.

Med `as_product` definert som i prod-veiledningen:

```sh
as_product podman ps
as_product podman inspect --format '{{.State.Health.Status}}' myproduct-todo-backend
as_product podman healthcheck run myproduct-todo-backend
```

En manuell sjekk i startperioden hoppes også over. `systemctl is-active` er
fortsatt ingen helsesjekk for enkeltcontainere. Rootless Podman bruker transient-
timere i tjenestebrukerens systemd-instans; linger må være aktiv.

## Legge til en app

Et manifest i `manifests/` gjør appens image synlig for bundle-byggingen.
Det finnes ikke et appregister. Gå gjennom punktene under når du legger til en app;
database og OIDC trengs bare for apper som bruker dem.

| Behov | Filer og endringer |
| --- | --- |
| Kode og image | `apps/<app>/Containerfile`; legg app og riktig tagg til i `dev/build-images.sh`, eller bygg/pull imaget manuelt. |
| Pod | `manifests/NN-<app>.yaml`: fullt image-navn, `imagePullPolicy: Never`, `restartPolicy: Always`. |
| Helsesjekk | Én lokal exec-basert `livenessProbe` per container: initialDelay 90, period 30, timeout 5, failureThreshold 3. Init-containere har ingen probe. |
| Produkttester | Oppdater de faste ressurstallene i `test_real_product_manifests_render_with_dummy_files` i `tests/test_deploy.py`; `tests/test_health.py` kontrollerer alle prober automatisk. |
| Proxy-rute | Ny `location` i `apps/proxy/default.conf`; bygg proxy-imaget på nytt. |
| Database | Egen postgres-pod etter mønster fra `30-identity-postgres.yaml`/`40-todo-postgres.yaml`, PVC i `20-storage.yaml`, passordfil og `SECRET_FILES` i config. For nye installasjoner oppdateres også `scripts/generate-certificates.sh`. |
| OIDC | Klient, redirect-URI og scope i `apps/identity/Program.cs`; klientsertifikat og Secret/PVC i config og manifest. Bygg identity-imaget på nytt. |
| E2E | Ny kontroll i `dev/smoke-test.py`, kalt fra `main`; prøv frontend-JavaScript i nettleser. |
| Akseptanse | `healthy()` i `acceptance/remote.sh` leser navn fra installert YAML; legg til nødvendige DB-/OIDC- og e2e-kontroller. |
| Dokumentasjon | Oppdater appoversikt, Secret-volumer ved avinstallering, `acceptance/README.md` og `examples/VM-CHECKLIST.md`. |

Kjør enhetstester, `./deploy prepare` og dev-e2e før du bygger bundlen.
Ny tagg i manifestet krever at nøyaktig det navnet er bygget eller hentet lokalt.
Ved utvidelse av en eksisterende installasjon opprettes bare nye hemmeligheter,
som beskrevet under oppgradering; behold alle eksisterende filer.

## Offline-bundle og rootless Quadlet

Manifestene er eneste kilde for images. Byggingen leser `containers` og
`initContainers` fra alle `manifests/*.yaml`, fjerner duplikater og sorterer navnene.
Images må allerede være hentet med `podman pull` eller bygget med `podman build`
på byggemaskinen, med nøyaktig samme fulle navn og tagg som i manifestet.
`./dev/build-images.sh` gjør dette for demoen.

Bruk helst fulle originalnavn, for eksempel `registry.firma.no/team/app:1.2.3`,
og `imagePullPolicy: Never`. Også `localhost/myapp:1.0.0` og navn med registry-port
godtas. Korte navn som `postgres:16` og `team/app:1` avvises. Placeholders i
image-navn støttes ikke ved bygging, og manifestene må inneholde minst ett image.
Bundlen trenger ingen separat image-liste: ved en ny image-versjon endres taggen
i manifestet, og det nye imaget må finnes lokalt før bygging. Demoens
`dev/build-images.sh` har derimot en fast appliste og tagg som også må oppdateres
hvis du bruker scriptet til å bygge en ny app eller versjon.

Kjør `./build-bundle.sh` med Podman 4.4 eller nyere. `bundle.py` bruker
`podman save -m` med standardformatet docker-archive og lager
`dist/myproduct-0.1.0-offline.tar.gz` med manifests, deploy, scripts, Quadlet og
checksums. `images/images.tar` er ett arkiv med alle imagene og deres fulle navn
og tagger. `images/images.txt` lister navnene, ett per linje. Begge filene inngår
i checksums. Private nøkler, lokal config og PKI blir ikke pakket med.

På målmaskinen brukes en egen systembruker `myproduct`, med hjem
`/var/lib/myproduct` (0700), rootless Podman og linger. Forutsetninger på verten:
Podman 5.x med bruker-Quadlet, Python 3.6+/PyYAML, OpenSSL, `newuidmap`/`newgidmap`,
`semanage`, `restorecon`, aktiv firewalld og SELinux Enforcing. På OL9 leveres
`semanage` av `policycoreutils-python-utils`; klargjør dette før maskinen isoleres.
Ingen pakker installeres av produktet.

### Første installasjon

Følgende kjøres som vanlig operatør med sudo, fra katalogen med arkivet og
checksum-filen. Tilpass versjon, IP, vertsnavn og port. Vertsnavnet må stemme med
DNS, sertifikatet og `PUBLIC_ORIGIN`; `HTTPS_PORT` og porten i `PUBLIC_ORIGIN`
må endres sammen. Demoens interne OIDC-navn er `myproduct-proxy`.
Rediger `IP_ADDRESS`, `PUBLIC_ORIGIN` og `HTTPS_PORT` i config med sudoedit.
Porten må være identisk i `--port`, `HTTPS_PORT` og `PUBLIC_ORIGIN`.

`fapolicyd-cli --update` varsler daemonen og venter ikke på ferdig oppdatering.
Definer denne funksjonen i operatørens shell før installasjon eller oppgradering.
Den leser databasen inntil nye og eventuelt fjernede stier stemmer, og stopper
ved feil eller tidsavbrudd. Bare stier og status skrives ut.

```sh
# Vent lesende på eksakte trust-stier etter daemonens asynkrone oppdatering.
wait_trust() {
    local wanted=$1 removed=${2:-} dump status attempt
    for attempt in {1..30}; do
        dump=$(timeout 10 sudo -n fapolicyd-cli --dump-db) || {
            echo 'FAIL: could not read trust database' >&2; return 1;
        }
        status=0
        awk -v wanted="$wanted" -v removed="$removed" '
            {
                path=$0
                sub(/^[^[:space:]]+[[:space:]]+/, "", path)
                sub(/[[:space:]]+[0-9]+[[:space:]]+[[:xdigit:]]+[[:space:]]*$/, "", path)
                if (NF < 4 || path !~ /^\// || $(NF-1) !~ /^[0-9]+$/ ||
                    length($NF) != 64 || $NF !~ /^[[:xdigit:]]+$/) invalid=1
                if (path == wanted) found=1
                if (removed != "" && path == removed) old=1
            }
            END { if (NR == 0 || invalid) exit 2; if (!found || old) exit 1 }
        ' <<< "$dump" || status=$?
        case "$status" in
            0) printf 'PASS: trust ready for %s; removed=%s\n' "$wanted" "${removed:-none}"; return;;
            1) printf 'WAIT: trust update pending for %s; removed=%s (%s/30)\n' "$wanted" "${removed:-none}" "$attempt";;
            *) echo 'FAIL: invalid or empty trust database output' >&2; return 1;;
        esac
        if [[ $attempt != 30 ]]; then sleep 1; fi
    done
    echo 'FAIL: trust update did not finish within 30 checks' >&2
    return 1
}
```

```sh
version=0.1.0
hostname=myproduct-proxy
https_port=8443
archive="myproduct-$version-offline.tar.gz"
release="/var/lib/myproduct/releases/myproduct-$version"
sha256sum -c "$archive.sha256"
stage=$(mktemp -d /tmp/myproduct-install.XXXXXXXX)
tar xzf "$archive" -C "$stage"
sudo bash "$stage/myproduct-$version/scripts/prepare-host.sh" --port "$https_port"
sudo -H -u myproduct mkdir -p /var/lib/myproduct/releases
# Operatøren åpner arkivet: myproduct trenger ikke tilgang til operatørens hjem.
sudo -H -u myproduct tar xzf - -C /var/lib/myproduct/releases < "$archive"
rm -rf -- "$stage"
sudo bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$release"
sudo fapolicyd-cli --file add "$release/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py"
sudo -H -u myproduct bash "$release/scripts/generate-certificates.sh" --root /var/lib/myproduct "$hostname"
sudo install -o myproduct -g myproduct -m 0600 "$release/config.example.yaml" /var/lib/myproduct/config.yaml
sudoedit /var/lib/myproduct/config.yaml
sudo -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$release"
sudo systemctl --user -M myproduct@ status myproduct.service
```

Operatøren trenger ikke `cd` inn i tjenestebrukerens private hjem. `sudo -H`
setter riktig HOME, men endrer ikke arbeidskatalogen. Derfor gjør bash et
uttrykkelig `cd` som tjenestebrukeren før install: rootless Podman må kunne åpne
arbeidskatalogen igjen når prosessen startes i brukerens navnerom. Operatørens
private hjem er ikke tilgjengelig for tjenestebrukeren. `sudo bash` leser
klargjøringsscriptet fra `/tmp`; scriptet startes ikke direkte, så `noexec` på
`/tmp` hindrer ikke denne kjøreformen. En eventuell policyavvisning skal fortsatt
undersøkes, ikke omgås med endrede tillatelser eller bred trust.

`prepare-host.sh --port <port>` er idempotent og krever heltall 1024–65535.
Det leser ingen config og har ingen eksempel-fallback. Scriptet oppretter
kontoen med nologin, tildeler minst 65536 subuid/subgid uten overlapp, setter
hjemmets mode, aktiverer linger og åpner porten permanent i firewalld.
Alle kontroller gir tydelige feil. En uventet ekvivalens som begynner med
`/var/lib/myproduct` gir stopp og må fjernes manuelt før klargjøring.

Systembrukeren får ikke de vanlige HOME_DIR-reglene fra container-selinux.
Lageret bruker derfor ekvivalensen
`/var/lib/myproduct/.local/share/containers = /var/lib/containers`, som beskrevet
[i Podmans feilsøkingsguide punkt 11](https://github.com/containers/podman/blob/main/troubleshooting.md#11-changing-the-location-of-the-graphroot-leads-to-permission-denied).
Overlay, overlay-layers og overlay-images har container_ro_file_t;
overlay-containers har container_var_lib_t; voluminnhold har container_file_t.

Scriptet preoppretter `.config/cni/net.d`, cni.lock og brukerens Quadlet-katalog
før første Podman-kall. Dette forebygger runtime-typen på config-stiene som ble
observert i run-6. Det merker hjemmet med storage ekskludert, og bare selve
storage-katalogen uten rekursjon. **Kjør aldri restorecon -R eller -F på et fylt
lager.** Scriptet endrer ikke SELinux/fapolicyd sin enforcing-tilstand.

Akseptansesteg 07 sammenligner faktiske typer mot selinux.matchpathcon. Utenfor
storage skal `restorecon -n -v -R -e <storage> /var/lib/myproduct` gi tom output.
Lagerets separate dry-run logges alltid og hver linje må passe en begrunnet,
navngitt regel; ukjente linjer gir FAIL. Se [SELinux-diagnosen](acceptance/SELINUX-DIAGNOSIS.md).
Ingen AVC/USER_AVC/FANOTIFY-avvisninger tillates. Rootless bruker en vanlig
vertssocket på port 1024 eller høyere; lab-filteret avgrenser til lab-subnettet.

Sertifikatgenereringen ovenfor er for demo/test. I ekte produksjon utstedes
sertifikatene utenfor målmaskinen og leveres til stiene i config. CA-ens private
nøkkel skal ikke kopieres dit.

`install` leser config.yaml i hjemmet fra brukerdatabasen (`pwd.getpwuid`).
Alle prod-stier følger dette hjemmet; install avviser en satt `$HOME` som
avviker, for eksempel ved feil sudo-konfigurasjon. `prepare` leser fortsatt config i repo-roten.
Relative stier i `SECRET_FILES` og `VOLUME_FILES` regnes fra config-filens
katalog. Absolutte stier og `~` virker som før. Dermed kan eksempelconfigens
stier brukes uendret både i dev og prod.

`install` avviser root, kontrollerer runtime-katalogen og rendrer YAML. Hvis
`XDG_RUNTIME_DIR` mangler, brukes `/run/user/<euid>`. En satt variabel må være
nøyaktig denne stien; avvik avvises før rendering. Manglende katalog gir en
feil med hint om linger. Deretter kjøres `podman load -i images/images.tar`
og `podman image exists` i tjenestebrukerens lager. Først etter vellykket
image-kontroll skrives filarkiver og Quadlet-filer, og `systemctl --user`
kjører daemon-reload, restart og is-active. `prepare` er uendret.

```text
/var/lib/myproduct/                         0700, eid av myproduct
├── config.yaml                            0600, brukes av alle versjoner
├── generated-certificates/                 0700, varige nøkler og passord
├── PKI/private/                            0700, demo-CA
├── .config/containers/systemd/
│   ├── myproduct.kube                     0644
│   ├── myproduct.network                  0644
│   └── myproduct.yaml                     0600 (inkluderer secrets)
├── .local/share/containers/storage/        images, volumer og databaser
├── files/                                 0700; tar-arkiver 0600
└── releases/myproduct-<versjon>/            kode, manifester og images; kan slettes
```

`myproduct.network` oppretter nettverket automatisk og gir hovedtjenesten en
avhengighet til `myproduct-network.service`. Alle pods beholder
`restartPolicy: Always`. Bruker-Quadlet bruker `WantedBy=default.target` og
linger for oppstart uten innlogging. Podman 5.x legger til
`podman-user-wait-network-online.service`; kontroller generatoren som brukeren:

```sh
# Bruk denne funksjonen også til Podman-kommandoene ved drift/avinstallering.
as_product() {
    sudo -H -u myproduct bash -c '
        cd "$HOME" || exit
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        exec "$@"
    ' bash "$@"
}
as_product /usr/lib/systemd/user-generators/podman-user-generator --dryrun
```

`myproduct.kube` gir én tjeneste, `myproduct.service`, for alle pods. Hver
installasjon, også en oppgradering, restarter alle pods og databasene.
Tjenesten feiler hvis en pod feiler ved oppstart. Det er ingen startrekkefølge
mellom pods; appene prøver å koble til databasen i 60 sekunder. Det er én
installasjon per tjenestebruker, med faste navn på tjenesten og nettverket.
`systemctl is-active` viser tjenestens tilstand og garanterer ikke at hver
container kjører. Ved driftskontroll må også containerstatus og HTTPS/e2e
kontrolleres; tjenesten kan være aktiv selv om én container er stoppet.

### Oppgradering

Config, nøkler, passord, CA og Podman-lageret tilhører installasjonen, ikke en
release. **Ikke kjør generate-certificates.sh ved oppgradering**, og ikke kopier
ny eksempelconfig over eksisterende config. PostgreSQL setter passordet bare
ved første initialisering, demobrukerne beholder sine gamle passordhasher,
og klientene må fortsatt stole på samme CA. Scriptets sperre mot eksisterende
nøkler beholdes også når `--root` brukes.

Hvis en ny app krever et nytt databasepassord, opprett bare den nye filen før
installasjonen. Eksempel for en ny `new-app-db`-id (bytt navn i både config og manifest):

```sh
sudo -H -u myproduct bash -c '
    set -euC
    umask 077
    mkdir -p "$HOME/generated-certificates/new-app-db"
    openssl rand -hex 32 > "$HOME/generated-certificates/new-app-db/password"
'
sudoedit /var/lib/myproduct/config.yaml
```

`set -C` nekter å overskrive en eksisterende passordfil. Legg den nye stien til
under `SECRET_FILES`, og oppdater andre config-verdier den nye appen trenger.
Nye signerings-/klientsertifikater utstedes separat, i ekte prod av ekstern CA,
og leveres som tjenestebrukeren med `umask 077` til nye stier. Oppdater også
Duendes offentlige klientsertifikat/klientkonfigurasjon ved behov. Ikke erstatt
eksisterende CA, DB-passord, demopassord eller nøkler ved å kjøre hele generatoren.

Kjør fra katalogen med det nye arkivet og checksum-filen:

```sh
old_version=0.1.0
version=0.1.1
archive="myproduct-$version-offline.tar.gz"
release="/var/lib/myproduct/releases/myproduct-$version"
sha256sum -c "$archive.sha256"
sudo -H -u myproduct tar xzf - -C /var/lib/myproduct/releases < "$archive"
sudo bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$release"
sudo fapolicyd-cli --file add "$release/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py"
sudo -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$release"
sudo systemctl --user -M myproduct@ is-active myproduct.service
```

Kontroller at installasjonen lyktes, at tjenesten er aktiv og at alle
containere kjører. Hvis noe feiler, stopp her og behold gammel trust. Etter
vellykket installasjon og kontroll fjernes trust for den gamle releasen:

```sh
sudo fapolicyd-cli --file delete "/var/lib/myproduct/releases/myproduct-$old_version/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py" "/var/lib/myproduct/releases/myproduct-$old_version/deploy.py"
```

Etter vellykket oppgradering kan gamle release-kataloger slettes når deres
trust er fjernet. Behold `/var/lib/myproduct/config.yaml`,
`generated-certificates/`, `PKI/`, `files/` og Podman-lageret, også ved sletting
av releaser. Ta sikkerhetskopi av varig tilstand, inkludert databasene.
`PKI/private/ca.key` på verten er bare for demo; i ekte prod utstedes
sertifikatene eksternt og leveres til `generated-certificates/` uten CA-nøkkelen.

### fapolicyd og rootless

Checksum-kontrollen inne i bundlen kjøres som root: labens policy tillater
root med et betrodd RPM-program å lese også Python-filer. Deretter legges bare
den verifiserte `deploy.py` til i trust-databasen, slik at Python kjørt som
`myproduct` kan lese den. Gjenta checksum og trust for hver ny utpakket versjon.
Shell-script kjøres med `bash`, som leser filene uten direkte scriptkjøring.
Ingen kataloger, container-runtime eller private nøkler legges til i trust.

På OL9.8-laben feiler selv `sudo crun --version` med fapolicyd regel 5.
Audit viser cruns `open_tree` på `/proc/self/exe`, `mount_setattr` og `execveat`,
deretter `exe=/` og avvisninger ved åpning av biblioteker. Dette støtter
forklaringen om kjøring fra en løsrevet mount som fapolicyd ikke har observert,
slik at prosessen klassifiseres som direkte startet dynamisk laster.
[Red Hat beskriver samme symptom](https://access.redhat.com/solutions/7072618).

Rootless-modellen bruker et eget mount-namespace. Med labens
`allow_filesystem_mark = 0` forventes containerne å være utenfor fapolicyds
observasjon; dette er ikke en godkjenning av innholdet fra fapolicyd.
SELinux forblir Enforcing. Denne forklaringen må skilles fra faktisk
prod-verifikasjon: akseptansetest og audit skal dokumentere hva som virker på
målmaskinen. Ingen crun-regler, brede trust-regler eller binærendringer brukes.

## Secrets på disk og avinstallering

Podman kube play skriver Secret-innhold til navngitte volumer under
`/var/lib/myproduct/.local/share/containers/storage/volumes/<secret-navn>/_data/`.
Hjemmet er 0700, men private nøkler og passord blir liggende etter `kube down`
eller stopp. Filer fjernet fra Secret-definisjonen kan fortsatt ligge i volumet;
definerte filer overskrives. Secret-, PVC- og ConfigMap-navn må være unike.
`defaultMode: 0400` beskytter private nøkler inne i containeren, men sletter ikke
data fra vertens disk.

Stopp tjenesten før et Secret-volum slettes. Kommandoene nedenfor utføres av
operatøren. Gjenta trust-sletting for hver installert release som skal fjernes:

```sh
sudo systemctl --user -M myproduct@ stop myproduct.service
as_product podman volume ls
# Eksempel; slett bare identifiserte volumer som ikke skal bevares.
as_product podman volume rm identity-signing
sudo fapolicyd-cli --file delete "$release/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
sudo -H -u myproduct rm /var/lib/myproduct/.config/containers/systemd/myproduct.{kube,network,yaml}
sudo systemctl --user -M myproduct@ daemon-reload
sudo loginctl disable-linger myproduct
```

Secret-volumene er `identity-signing`, `identity-client-certificate`,
`identity-database-password`, `identity-demo-users`, `todo-database-password`
og `web-tls`. Behold database-/appdatavolumer med mindre de bevisst skal slettes.
Ikke slå på `KubeDownForce`: det kan også slette databasevolumene.
Når alle data bevisst skal fjernes, kan administrator stoppe brukerinstansen,
slette brukeren/hjemmet og fjerne SELinux-ekvivalensen:

```sh
sudo systemctl stop "user@$(id -u myproduct).service"
sudo userdel -r myproduct
sudo semanage fcontext -d /var/lib/myproduct/.local/share/containers
```

Volumsletting eller `userdel` garanterer ikke fysisk sletting fra disk eller
sikkerhetskopier. Installasjonsflyten forutsetter en ren prod-vert. Bruk [akseptansetesten](acceptance/README.md)
for prod-verifikasjon med systemd og reboot.
