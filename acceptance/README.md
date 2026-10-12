# Akseptanse: dev → bundle → offline prod

Kjør fra kontrolleren (Linux-laptop med Python 3.11+, git, SSH og scp):

```sh
python3 acceptance/acceptance.py --run 2026-10-12-run-3 run
```

**Dette ruller begge konfigurerte VM-er tilbake til snapshots og sletter deres
nåværende tilstand.** Bruk bare de to disponible lab-VM-ene. En kjøring er
samtykke til rollback, nettisolasjon, installasjon og reboot i disse VM-ene.
Ingen root-tilgang på kontrolleren trengs. Alle controller-verktøy bruker bare
Python-standardbiblioteket. VM-1 bruker en separat venv til HTTP-testene.

## Engangsoppsett

1. Opprett to Oracle Linux 9-VM-er på lab-nettet. Bruk samme CPU-arkitektur,
   tilstrekkelig disk til .NET/Python/nginx-images og bundle, SELinux enforcing
   og aktiv firewalld. VM-2 er det herdede produksjonsmålet og skal ha aktiv
   fapolicyd. VM-1 er utviklermaskinen, tilsvarende laptopen i `podman_test`,
   og skal ha fapolicyd inaktiv og deaktivert. Den forskjellen etableres bare
   ved opprettelse av `clean-dev`, ikke under en akseptansekjøring.
   VM-1 skal ha internett. VM-2 trenger internett bare under denne forberedelsen.
2. Installer forutsetningene **før snapshot**, på begge VM-er:

   ```sh
   sudo dnf install -y podman python3 python3-pyyaml openssl curl git tar gzip nftables firewalld fapolicyd policycoreutils-python-utils
   sudo systemctl enable --now firewalld
   python3 -c 'import yaml, venv'
   podman --version
   test -x /usr/lib/systemd/user-generators/podman-user-generator
   ```

   VM-1 må kunne bygge rootless og laste ned Python-pakker. Systemets Python på
   VM-2 med PyYAML er tilstrekkelig; ingen pip-installering der. Bruk Podman med
   bruker-Quadlet og multi-image-save (Podman 5.x); faktiske versjoner registreres i rapporten.
   Ingen app-images skal forhåndslastes for å skjule mangler i bundlen.
3. Legg laptopens SSH-nøkkel i brukerens authorized_keys og bekreft SSH-hostnøkler
   på laptop. Testen bruker `StrictHostKeyChecking=yes`. Aktiver lingering for
   labbrukeren slik at rootless containere og runtime-katalogen overlever SSH:

   ```sh
   sudo loginctl enable-linger "$USER"
   printf '%s ALL=(ALL) NOPASSWD: ALL\n' "$USER" | sudo tee /etc/sudoers.d/90-offline-acceptance
   sudo chmod 0440 /etc/sudoers.d/90-offline-acceptance
   sudo visudo -c
   sudo -n true
   ```

   Dette er lab-rettigheter, ikke en produksjonsanbefaling. Journalen bør være
   persistent. Kontroller klokke/NTP før offline-testen.
4. Lag en Proxmox API-tokenbruker avgrenset til disse to VM-ID-ene med
   `VM.Audit`, `VM.PowerMgmt`, `VM.Snapshot.Rollback`, samt audit-tilgang til
   task-status, HA og brannmurinnstillinger. Tokenet trenger ingen rett til å
   endre node-/datacenterbrannmur. Lag tokenfil med mode 0600 utenfor Git:

   ```text
   PVE_HOST=<DNS-navn som matcher Proxmox-sertifikatet>
   PVE_NODE=<node>
   PVE_TOKEN_ID=<user@realm!token>
   PVE_TOKEN_SECRET=<hemmelig verdi>
   PVE_CA=/absolutt/sti/pve-root-ca.pem
   ```

   Eksisterende token og CA fra `podman_test` kan brukes. TLS-kjede og vertsnavn
   verifiseres; bare Pythons nyere STRICT-krav til Key Usage i Proxmox-root-CA
   fravikes, som i inspirasjonsrepoets klient. Tokenet sendes bare i HTTP-header.
5. Kontroller at begge VM-er er rene: ingen pods, containere, volumer eller
   Secrets i verken rootless eller rootful lager; ingen
   `/etc/containers/systemd/myproduct.*`; ingen bruker `myproduct` eller
   `/var/lib/myproduct`. Disse tilstandskravene kontrolleres etter rollback,
   før isolasjon/installasjon (eksisterende feilet kjøring kan ligge før rollback). Ikke ha lab-VM-ene under Proxmox HA.
   Slå av VM-ene ryddig, ta snapshot `clean-agent` og start dem igjen. Snapshotet
   skal inneholde SSH/sudo, pakker og nett, men ingen applikasjonstilstand.
   Dette tilsvarer forberedelsen i `podman_test` sitt
   `deploy/scripts/lab/prepare-agent-snapshots.sh`. Ikke kjør det scriptet blindt:
   det har labspesifikke VM-ID-er og overskriver gjestetilstand.
   For VM-1 lages et separat snapshot fra `clean-agent` med scriptet nedenfor.
   Det opprinnelige snapshotet beholdes for `podman_test`. Ingen pakker,
   trust-regler, SELinux- eller brannmurinnstillinger endres.

6. Proxmox VM-brannmur skal være deaktivert og NIC-er tilkoblet i baseline.
   Snapshot rollback nullstiller ikke nødvendigvis eksterne brannmurregler.
   Readiness avviser avvik; den endrer ikke node-/datacenterregler.
7. Kopier `lab.example.env` til
   `~/.config/podman-offline-acceptance/lab.env`, fyll inn verifiserte verdier,
   sett katalogen til 0700 og filen til 0600. Ingen gjetting av VM-ID/IP.
   `LAB_CIDR` er det faktiske lab-subnettet (/24 eller smalere).
   `PROD_HOST` er appens navn, ikke nødvendigvis VM-ens OS-vertsnavn. Nåværende
   produkt bruker `myproduct-proxy`, som også løses internt av Podman DNS.
   Ekstern HTTP-test bruker `CONNECT_IP` og trenger ikke endring i `/etc/hosts`.

## Lag utviklerprofilen én gang

Etter at konfigurasjonsfilen over er fylt ut, kjør på kontrolleren:

```sh
mkdir -p -m 700 ~/podman-offline-acceptance-runs/preparations
# Bruk et nytt loggfilnavn og bevar loggen.
(umask 077; python3 acceptance/prepare_dev_snapshot.py --create   > ~/podman-offline-acceptance-runs/preparations/clean-dev.log 2>&1)
```

Scriptet stopper VM-en som er konfigurert som DEV, ruller den tilbake til
`clean-agent`, starter den, kontrollerer baseline og kjører nøyaktig
`sudo systemctl disable --now fapolicyd`. Det kontrollerer fortsatt Enforcing
og aktiv firewalld, stenger ned VM-en ryddig, oppretter `clean-dev` og starter
igjen med ny profilkontroll. Det avviser et eksisterende `clean-dev`, kontrollerer
at `clean-agent` sin snapshot-konfigurasjon er bevart og sender ingen operasjoner
til PROD. Oppdater så lokal `lab.env` til `DEV_SNAPSHOT=clean-dev`;
`PROD_SNAPSHOT=clean-agent` beholdes.

Readiness krever DEV: fapolicyd inactive/disabled, PROD: fapolicyd active,
og begge: SELinux Enforcing og firewalld active. Profilene registreres før
rollback og kontrolleres igjen fra snapshotene etter rollback. Feil profil
gir stopp, aldri automatisk endring. Begge VM-er må derfor være startet med
riktig profil før readiness.

## Kjøring og bevis

Commit først testkode og eventuelle tillatte smoke-endringer: readiness krever
ren checkout. Ingen push trengs: en Git-bundle av nøyaktig HEAD sendes til VM-1
og klones der. Dermed er både lokale commits og offline Git-tilgang støttet.
Produktets offline-bundle bygges deretter med det uendrede byggescriptet.

Stegene utføres i oppgavens rekkefølge. VM-2 isoleres **før overføring**, med
et separat nftables-filter og en aktivert systemd oneshot-enhet før nettstart.
Bare innkommende SSH/HTTPS fra lab-subnettet tillates, i tillegg til etablert
trafikk og Podmans interne DNS. Utgående trafikk utenfor lab-nettet blokkeres,
og eksterne DNS-forespørsler blokkeres også mot labens DNS-server. Internt
Podman-nett tillates. IPv6 får ingen ekstern utgående tillatelse.
Firewalld forblir aktiv; HTTPS-åpning for lab-subnettet er et dokumentert
installasjonskrav. Ingen innkommende databaseporter åpnes.

Isolasjon bevises med registry-curl, offentlig DNS-oppslag og et mislykket pull,
og gjentas etter reboot. Et mislykket programoppslag teller ikke som nettbevis.
Testens bevis-pull skjer før installasjon; senere journalføring av produktets
pull-forsøk starter først ved install. Nettisolasjonen fjernes ikke etterpå.

Rapporter og artefakter ligger i
`~/podman-offline-acceptance-runs/<run-id>/` (0700), utenfor Git:

- `logs/<steg>.log`: tidspunkt, eksakt kommando og eventuell stdin-kode, full
  output og exit-koder. Forventede feil i blokkeringstestene er eksplisitt merket.
- `record.jsonl`: ett sluttresultat per steg med varighet og loggsti.
- `REPORT.md`: dom, revisjon, ren checkout, VERSION, bundle-SHA256, VM-fakta,
  boot-ID-er og tidsbruk. Felt som ikke ble nådd, finnes ikke.
- `EVIDENCE.md`: generert rapport pluss utdrag og SHA256 for hver full logg.
- Kilde-Git-bundle og produktbundle/checksum når disse stegene er nådd.

Første feil gir `NOT CLEAN` og stopper alle følgende teststeg. Etter en feil kjøres bare lesende
innsamling av prod-audit og opprydding av overførte hemmeligheter. Også en Podman `Error:` med
exit 0 regnes som feil. Run-id og steg kan aldri gjenbrukes. Readiness kan
feile før rollback: da er ingen ren-start-test gjennomført, og rapporten sier det.
Ikke reparer VM-er eller endre kode midt i en kjøring. Ingen automatiske nye runs.

CA-sertifikat og demo-passord overføres med scp til 0700-kataloger under
`$XDG_RUNTIME_DIR` på kontroller og VM-1. Ingen private signerings-/CA-nøkler
flyttes. Passord logges ikke; kjente token/passord maskeres også i loggskriveren.
`10-cleanup` fjerner overførte filer, også etter feil. Hvis SSH til VM-1 er nede,
blir oppryddingen feil og dommen kan ikke bli CLEAN PASS; den fjernliggende
runtime-katalogen må da fjernes ved gjenopprettet tilgang/reboot. SIGKILL/strømtap
kan avbryte cleanup; behold run-mappen og bruk en ny run-id ved neste forsøk.
Produktets egne Secret-volumer på VM-2 blir liggende som bevis etter stopp.

## Hva testen faktisk krever

Revisjonen etter review bruker allerede Always, network-Quadlet, navnekontroll
og utsatt arkivskriving. Testen oppretter derfor ikke produktnettverket manuelt.
Den sjekker også hjelp-appen og alle sju appcontainere i seks pods.

Oppgavens `sudo -u myproduct podman kill myproduct-todo-backend` beholdes bokstavelig.
Podman dokumenterer at eksplisitt kill/stop ikke aktiverer restart-policyen:
https://docs.podman.io/en/v5.7.0/markdown/podman-run.1.html . Dette steget kan derfor
stoppe selv med Always. Det erstattes ikke med direkte prosessignal for å få
PASS. Rapporten skiller dette akseptansekravet fra et faktisk applikasjonskrasj.
Markører opprettes for Alice og Bob, sjekkes etter start/restart/kill/reboot og
beholdes i databasen for inspeksjon. HTTP-testene kjører ikke JavaScript i nettleser.

## Lokale kontroller av testrammen

```sh
python3 -m unittest discover -s acceptance -p 'test_*.py'
bash -n acceptance/remote.sh
ruff check acceptance/ scripts/smoke-test.py
ruff format --check acceptance/ scripts/smoke-test.py
pyright acceptance/ scripts/smoke-test.py
```

Testene stubber/simulerer feil og dekker stoppregler, maskering av hemmeligheter,
opprydding, dupliserte run-id-er/steg og at ufullstendige runs aldri blir CLEAN PASS.

## Prod-operatør og audit-bevis

Prod kjøres som labbrukeren med sudo akkurat som i produktets [README](../README.md):
midlertidig utpakking, prepare-host, release under /var/lib/myproduct, indre
checksums som root og trust av bare deploy.py, sertifikat/config som myproduct,
og install som myproduct. Brukerens HOME settes med sudo -H. Ingen rootful
produktressurser skal opprettes. Steg 07 sjekker eierskap/mode, SELinux-labels,
bruker-generatorens nettavhengighet og at rootful containerlager er tomt.
Prepare-host åpner HTTPS i firewalld; nft-filteret avgrenser til lab-subnettet.

CA og passord leses via sudo som myproduct direkte til private filer på
kontrolleren, aldri til logg; deretter scp til VM-1 sin private runtime-katalog.
Livssyklus bruker systemctl --user -M myproduct@, og Podman som myproduct med
brukerens XDG_RUNTIME_DIR. Reboot skal virke uten innlogging som myproduct.

Når PROD har blitt rullet tilbake og SSH er tilgjengelig, hentes FANOTIFY,
AVC og USER_AVC til slutt, både ved suksess og ved feil. Starttid lagres som epoch.
VM-ens ausearch forventer dato i lokalens %x-format og tid som et eget argument:

```sh
start_date=$(LC_ALL=C date -d "@$run_started" +%x)
start_time=$(date -d "@$run_started" +%H:%M:%S)
sudo env LC_ALL=C ausearch --input-logs -m FANOTIFY,AVC,USER_AVC -ts "$start_date" "$start_time" -i </dev/null
```

På OL9-laben betyr dette MM/DD/YY. Fire sifre i årstallet eller dato og tid i
ett argument blir avvist; dette ble kontrollert lesende før ny kjøring.
Hele audit-utdraget tas med i EVIDENCE.md, også avvisninger som ikke stoppet et
produktsteg. Ingen treff er gyldig; utilgjengelig audit gir NOT CLEAN.
Originalfeilen beholdes selv om audit-innsamlingen feiler. Gamle runs og
separate diagnoselogger endres aldri.
