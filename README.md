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
CRUD, tilgangsskille mellom brukere, CSRF-beskyttelse og lokal utlogging.
Den følger også hjelpelenkene fra Todo og kontrollerer sidene, navigasjonen,
stilarket, /help-redirect og 404 for ukjente hjelpesider. Den
verifiserer CA/vertsnavn og trenger ingen endring i `/etc/hosts`. Dette er en
HTTP-integrasjonstest; frontend-JavaScript må også prøves i en nettleser.
De isolerte renderer-/bundle-testene kjøres med `python3 -m unittest discover -s tests`.
Se også de små [Podman-eksemplene](examples/README.md).

Verifisert 2026-10-12 med ekte rootless Podman 5.7.0: alle seks pods starter,
og hele HTTP-integrasjonstesten passerer gjennom nginx. De 65 enhetstestene
passerer med både PyYAML 5.4.1 og 6.0.3. Ruff, Pyright og kontroll av Python
3.6-kompatibilitet for deploy/bundle/testene var rene ved denne dev-kjøringen.
Dette dokumenterer ikke prod-Quadlet eller reboot.

## Offline-bundle og rootless Quadlet

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

På målmaskinen brukes en egen systembruker `myproduct`, med hjem
`/var/lib/myproduct` (0700), rootless Podman og linger. Forutsetninger på verten:
Podman 5.x med bruker-Quadlet, Python 3.6+/PyYAML, OpenSSL, `newuidmap`/`newgidmap`,
`semanage`, `restorecon`, aktiv firewalld og SELinux Enforcing. På OL9 leveres
`semanage` av `policycoreutils-python-utils`; klargjør dette før maskinen isoleres.
Ingen pakker installeres av produktet.

Følgende kjøres som vanlig operatør med sudo, fra katalogen med arkivet og
checksum-filen. Tilpass versjon, IP, vertsnavn og port. Vertsnavnet må stemme med
DNS, sertifikatet og `PUBLIC_ORIGIN`; `HTTPS_PORT` og porten i `PUBLIC_ORIGIN`
må endres sammen. Demoens interne OIDC-navn er `myproduct-proxy`.

```sh
version=0.1.0
hostname=myproduct-proxy
ip_address=192.168.0.108
https_port=8443
archive="myproduct-$version-offline.tar.gz"
release="/var/lib/myproduct/releases/myproduct-$version"
sha256sum -c "$archive.sha256"
stage=$(mktemp -d /tmp/myproduct-install.XXXXXXXX)
tar xzf "$archive" -C "$stage"
python3 - "$stage/myproduct-$version" "$https_port" <<'PY'
import pathlib, sys, yaml
root = pathlib.Path(sys.argv[1])
config = yaml.safe_load((root / "config.example.yaml").read_text())
config["HTTPS_PORT"] = int(sys.argv[2])
(root / "config.yaml").write_text(yaml.safe_dump(config))
PY
sudo bash "$stage/myproduct-$version/scripts/prepare-host.sh"
sudo -H -u myproduct mkdir -p /var/lib/myproduct/releases
# Operatøren åpner arkivet: myproduct trenger ikke tilgang til operatørens hjem.
sudo -H -u myproduct tar xzf - -C /var/lib/myproduct/releases < "$archive"
rm -rf -- "$stage"
sudo bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$release"
sudo fapolicyd-cli --file add "$release/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
sudo -H -u myproduct bash "$release/scripts/generate-certificates.sh" "$hostname"
sudo -H -u myproduct cp "$release/config.example.yaml" "$release/config.yaml"
sudo -H -u myproduct python3 - "$release/config.yaml" "$ip_address" "$hostname" "$https_port" <<'PY'
import os, sys, yaml
with open(sys.argv[1]) as stream:
    config = yaml.safe_load(stream)
config.update(IP_ADDRESS=sys.argv[2], PUBLIC_ORIGIN="https://{}:{}".format(sys.argv[3], sys.argv[4]), HTTPS_PORT=int(sys.argv[4]))
os.chmod(sys.argv[1], 0o600)
with open(sys.argv[1], "w") as stream:
    yaml.safe_dump(config, stream)
PY
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

`prepare-host.sh` er idempotent. Det oppretter kontoen med nologin, tildeler
minst 65536 subuid/subgid uten overlapp, setter hjemmets mode, legger til
SELinux-ekvivalensen `/var/lib/myproduct = /home`, kjører restorecon og aktiverer
linger. HTTPS-porten leses fra config (eller eksempelconfig hvis config mangler),
åpnes permanent i firewalld og brannmuren lastes på nytt. Rootless bruker en
vanlig vertssocket; velg port 1024 eller høyere. I lab avgrenser nettisolasjonen
innkommende trafikk ytterligere til lab-subnettet. Scriptet endrer ikke SELinux
eller fapolicyd sin enforcing-tilstand. Kontroller faktisk SELinux-merking og
nettverk på målversjonen med akseptansetesten.

Sertifikatgenereringen ovenfor er for demo/test. I ekte produksjon utstedes
sertifikatene utenfor målmaskinen og leveres til stiene i config. CA-ens private
nøkkel skal ikke kopieres dit.

`install` avviser root, kontrollerer runtime-katalogen og rendrer YAML. Hvis
`XDG_RUNTIME_DIR` mangler, brukes `/run/user/<uid>`; manglende katalog gir en
feil med hint om linger. Deretter kjøres `podman load -i images/images.tar`
og `podman image exists` i tjenestebrukerens lager. Først etter vellykket
image-kontroll skrives filarkiver og Quadlet-filer, og `systemctl --user`
kjører daemon-reload, restart og is-active. `prepare` er uendret.

```text
/var/lib/myproduct/                         0700, eid av myproduct
├── .config/containers/systemd/
│   ├── myproduct.kube                     0644
│   ├── myproduct.network                  0644
│   └── myproduct.yaml                     0600 (inkluderer secrets)
├── .local/share/containers/storage/        images, volumer og databaser
├── files/                                 0700; tar-arkiver 0600
└── releases/myproduct-<versjon>/            utpakket bundle og lokal config/PKI
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
sudo semanage fcontext -d /var/lib/myproduct
```

Volumsletting eller `userdel` garanterer ikke fysisk sletting fra disk eller
sikkerhetskopier. Installasjonsflyten forutsetter en ren prod-vert. Bruk [akseptansetesten](acceptance/README.md)
for prod-verifikasjon med systemd og reboot.
