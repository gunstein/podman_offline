# Akseptanse: dev → bundle → offline prod

Kjør fra kontrolleren (Linux-laptop med Python 3.11+, git, SSH og scp):

```sh
python3 acceptance/acceptance.py --run 2026-10-12-run-12 run
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
`11-cleanup` fjerner overførte filer, også etter feil. Hvis SSH til VM-1 er nede,
blir oppryddingen feil og dommen kan ikke bli CLEAN PASS; den fjernliggende
runtime-katalogen må da fjernes ved gjenopprettet tilgang/reboot. SIGKILL/strømtap
kan avbryte cleanup; behold run-mappen og bruk en ny run-id ved neste forsøk.
Produktets egne Secret-volumer på VM-2 blir liggende som bevis etter stopp.

## Hva testen faktisk krever

Revisjonen etter review bruker allerede Always, network-Quadlet, navnekontroll
og utsatt arkivskriving. Testen oppretter derfor ikke produktnettverket manuelt.
Den sjekker også hjelp-appen og alle sju appcontainere i seks pods.

Etter godkjent endring av akseptansekravet tester `09-crash` et uventet
prosesskrasj. Steget leser PID, starttid og restart-teller fra inspect-JSON og
sender ett `sudo -n kill -KILL <verts-PID>`. Innen 60 sekunder kreves Running,
restart-teller økt med nøyaktig én, ny PID, ny starttid og ingen StoppedByUser.
Deretter kontrolleres alle containere og `/api/health` gjennom HTTPS-proxyen
med installasjonens CA før markørene leses.

`podman kill` brukes ikke til å simulere krasj: Podman merker dette som en
[eksplisitt brukerstopp](https://github.com/containers/podman/blob/v5.8.2/docs/source/markdown/options/restart.md)
og hindrer automatisk restart. Run-11 dokumenterer den tidligere testen;
dens resultat og bevis er bevart.
Markører opprettes for Alice og Bob, sjekkes etter start/restart/krasj/reboot og
beholdes i databasen for inspeksjon. HTTP-testene kjører ikke JavaScript i nettleser.

## Lokale kontroller av testrammen

```sh
python3 -m unittest discover -s acceptance -p 'test_*.py'
bash -n acceptance/remote.sh
ruff check acceptance/ dev/smoke-test.py
ruff format --check acceptance/ dev/smoke-test.py
pyright acceptance/ dev/smoke-test.py
```

De 67 lokale testene stubber/simulerer feil og dekker stoppregler, maskering av hemmeligheter,
opprydding, dupliserte run-id-er/steg og at ufullstendige runs aldri blir CLEAN PASS.

## Prod-operatør og audit-bevis

Prod kjøres som labbrukeren med sudo akkurat som i produktets [README](../README.md):
midlertidig utpakking, prepare-host, release under /var/lib/myproduct, indre
checksums som root og trust av bare deploy.py, sertifikater som myproduct,
config med install -o myproduct -g myproduct -m 0600,
og install som myproduct. Brukerens HOME settes med sudo -H, og bash bytter arbeidskatalog som
tjenestebrukeren før install og Podman. Dette er nødvendig når operatørens
hjem er 0700; sudo -H alene beholder den utilgjengelige arbeidskatalogen. Ingen rootful
produktressurser skal opprettes. Steg 07 sjekker eierskap/mode, SELinux-labels,
bruker-generatorens nettavhengighet og at rootful containerlager er tomt.
Steg 07 bruker samme Python-heredoc på stdin til sudo python3 som før.
Modulen selinux er påkrevd (policycoreutils-python-utils); fravær gir tydelig FAIL.
Policy-prober bekrefter ekvivalensen; faktiske typer sammenlignes med
selinux.matchpathcon med stat.S_IFMT(os.lstat(sti).st_mode) for eksisterende
stier. Bare de to eksplisitte policy-probene bruker modus 0. Lstat-feil gir
FAIL uten reserveoppslag; lenkemålet følges ikke. Overlay, overlay-layers og overlay-images er ro, men
overlay-containers er container_var_lib_t og voluminnhold container_file_t.
Utenfor storage kreves tom restorecon -n -v -R -e <storage> /var/lib/myproduct.
Storage dry-run logges separat og alle linjer må klassifiseres med [reglene og
run-6-tabellen](SELINUX-DIAGNOSIS.md). Ukjente linjer gir FAIL.
Ingen AVC/USER_AVC/FANOTIFY siden start tillates. Ingen labels repareres i
kontrollstegene, og ingen restorecon uten -n, -F eller chcon brukes der.
Klargjøringen ekskluderer storage fra rekursiv relabeling, også ved gjentakelse;
kjør aldri restorecon -R eller -F på et fylt lager.
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

## Varig tilstand og oppgradering

Første installasjon skriver config, generated-certificates og PKI direkte i
`/var/lib/myproduct`, utenfor releases. Steg 07 beholder CA-sertifikatets
SHA256-fingeravtrykk (DER) og filhashene for config, sertifikater, passord og CA
bare i minnet for sammenligning. Bevisene viser filnavn og «likt/endret»,
uten hashverdier eller filinnhold.

Etter livssyklus/reboot øker steg 10 patch-delen i VERSION bare i VM-1 sin
arbeidskopi. Git-diffen og ny versjon registreres; ingen commit eller andre
kodeendringer gjøres. Ny bundle bygges og overføres med separat SHA256 i
rapporten. Oppgraderingen følger README: checksums, trust av ny deploy.py,
install som tjenestebrukeren og helsekontroll før gammel trust fjernes. Ingen generering
eller config-kopiering. Testen krever uendrede filhashverdier og CA, full e2e
med de opprinnelig overførte passordene, bevarte todo-markører og at gammel
trust er borte. Steg 11 samler audit og rydder overførte hemmeligheter.
Hvis et tidligere steg stopper, er oppgraderingen ikke testet.

Kontroll A–E kjøres på nytt etter reboot og oppgradering. Hashsammenligningen
omfatter config, generated-certificates, PKI/private og files/. Begge e2e- og
markørkontrollene bruker de opprinnelige passordene.

### Maskinlesbare kommandosvar

Rammeverket fanger stdout og stderr separat. Bare stdout brukes som JSON,
runtime-sti, boot-ID eller i VM-kontrollenes strengsammenligninger. Stderr
logges under egen etikett, inkludert OpenSSH-advarselen om manglende
postkvante-nøkkelutveksling; advarselen navngis i rapporten. Ikke-null exit
stopper steget selv om stdout inneholder gyldige data. Tomme eller ugyldige
maskinlesbare svar stoppes også. Tomme ressurslister og restorecon-utskrifter
er forventede resultater i kontrollene som uttrykkelig krever det.

Audit har ett dokumentert unntak: `ausearch` returnerer 1, tom stdout og
`<no matches>` på stderr når ingen hendelser finnes. Andre audit-feil stoppes.
SSH-polling etter rollback/reboot og de eksplisitte isolasjonsprobene godtar
ventede feilstatuser. Pull-proben undersøker bare sin egen stderr for en konkret
nettfeil; stdout og stderr slås aldri sammen til et maskinlesbart svar.

Hashverdier for varige filer beholdes bare i kontrollerens minne gjennom
kjøringen. Logger, rapport og evidence inneholder bare filnavn og
«likt/endret» fra sammenligningen. Kommandoen leser filene for hashing og
skriver aldri filinnhold. Oversikten nedenfor beskriver stedene hvor
kommandosvar parses; den er dokumentasjon, ikke et automatisk testbevis.

Pull-proben beholder stdout og merker sin egen stderr med `pull-probe:`.
Exit 124 godtas som timeout. Exit 125 krever en konkret nettfeil i stderr
(lookup, dial tcp, i/o timeout, connection refused, network is unreachable
eller no such host); rettighets- og lagringsfeil gir FAIL. Vellykket pull og
andre statuser stopper steget. SSH-advarsler merkes ikke om.

Etter reboot venter `09-wait-boot-service` på automatisk oppstart i inntil
240 sekunder. `failed` stopper straks; steget starter eller restarter aldri
tjenesten. Sluttaudit bruker kontrollmodus etter fullført kjøring, slik at
avvisninger under de siste e2e-stegene også gir NOT CLEAN. Etter en tidligere
feil samles hendelsene fortsatt inn som bevis.

Ikke-tom stderr fra restorecon gir FAIL også ved exit 0. Regelen for
`CUSTOM_WRITABLE_LAYER` godtar bare UpperDir-lag fra inspect av eksisterende
containere; et image-lag med samme label godtas ikke.

### Oversikt over parsing av kommandosvar

- `acceptance.py`: `persistent_state` leser JSON; `credentials` validerer runtime-sti;
  `boot_id`, `wait_ssh` og `reboot` validerer boot-ID.
- `09-crash` parser inspect-JSON til fem validerte tilstandsfelt og logger bare
  disse. Starttiden behandles som én JSON-streng, også når den har mellomrom.
  `wait_backend` kontrollerer curl-exit og HTTP-status fra proxyen.
- `remote.sh`: `profile`/`facts` sammenligner getenforce og systemctl; `clean`,
  `check` og `stop` kontrollerer Podman-lister og find-output.
- `clone`, `bundle` og `upgrade-bundle` kontrollerer Git-status/diff; release-stegene
  leser VERSION og `upgrade` kontrollerer trust-databasen.
- `healthy` leser Podman-JSON; `check` kontrollerer generatoren og filtrert journal,
  bruker-ID og installasjonstid; `wait-boot-service` leser systemd-tilstand.
- LABELS leser UpperDir fra inspect og restorecon-linjer; `audit_events` leser
  ausearch-resultatet med adskilte strømmer.
- Snapshot-klargjøring sammenligner getenforce/systemctl. Proxmox-data er HTTP-JSON;
  markørkontrollen leser lokale JSON-filer og HTTP-svar.
- Git-revisjon/status, VERSION og record.jsonl på kontrolleren er lokale data.

Alle registrerte stderr-linjer som begynner med `WARNING`, `** WARNING` eller
`Warning:` navngis som «stderr warning» i rapporten. Kilden kan være SSH-klienten
eller fjernkommandoen; den utledes ikke fra teksten. Kjente hemmeligheter maskeres.
