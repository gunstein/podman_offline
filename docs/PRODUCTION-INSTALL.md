# Produksjonsinstallasjon: eksisterende bruker, data under /var/lib/<produkt>

**Status (backlog 64):** implementert og testet lokalt (produkt-, enhets- og
harness-tester). Den reelle OL9-kjøringen med SELinux Enforcing og fapolicyd
gjenstår; se `acceptance/PRODUCTION-LAYOUT.md` i kildekoden. Til den er kjørt
rent, er denne flyten ikke merket klar for kundeinstallasjon.

Denne veiledningen, [PFX-veiledningen](PFX-CREDENTIALS.md) og
[README](../README.md) følger med i hver komponent-release under
`/var/lib/sms/releases/<release>/`; lenkene virker der uten kildekoden.

Eksempelet bruker hele veien disse verdiene. Bytt dem ut; ingenting av dette er
hardkodet i produktet:

| Verdi | Eksempel | Merknad |
| --- | --- | --- |
| Produkt (`product:` i bundles.yaml) | `sms` | gir `/var/lib/sms` og unitnavn `sms-<komponent>` |
| Driftsbruker (eksisterende innloggingskonto) | `produser` | hjem, shell og UID beholdes uendret |
| Bundles | `sms-platform-1.4.2`, `sms-sts-2.0.1` | versjonene er uavhengige per komponent |
| Offentlig adresse | `https://sms.example.org:8443` | samme port i `--port`, `HTTPS_PORT` og `PUBLIC_ORIGIN` |

## Plassering

| Sti | Eier og modus | Innhold |
| --- | --- | --- |
| `~produser/.sms/sms.env` | produser, katalog `0700`, fil `0600` | eneste produktfil i hjemmekatalogen |
| `/var/lib/sms/` | root, `0755` | installasjonsrot; driftsbrukeren kan ikke erstatte innholdet |
| `/var/lib/sms/releases/` | root | publiserte, verifiserte releaser (skrivebeskyttet) |
| `/var/lib/sms/state/` | produser, `0700` | komponentconfig, credentials, installert metadata, registreringer, retry-status |
| `/var/lib/sms/config/` | produser, `0700` | Podmans og brukersystemd sin `XDG_CONFIG_HOME` (Quadlet-filer) |
| `/var/lib/sms/storage/` | produser, `0700` | Podmans `XDG_DATA_HOME`: images, volumer, cache |
| `/etc/systemd/system/user@<uid>.service.d/podman-offline-sms.conf` | root | gir brukersystemd samme `XDG_*`-verdier ved hver oppstart |

`/run/user/<uid>`, systemjournalen og `/etc` beholder sine vanlige plasseringer.

**Diskplass:** hjemmekatalogen trenger bare noen hundre byte. Under `/var/lib`
trengs ved publisering av hver release plass til arkivet to ganger (kopi og
utpakket release) i tillegg til eldre releaser frem til de pensjoneres, og i
`storage/` plass til alle images og databaser. `podman load` mellomlagrer i
`/var/tmp` (Podmans standard `image_copy_tmp_dir`); sett av like mye plass der
som største `images/images.tar`. Ikke legg arkiver i hjemmekatalogen.

## 1. Administrator: forutsetninger og overføring

Verten er Oracle Linux 9 med `getenforce` = `Enforcing`, aktiv fapolicyd og
firewalld, og pakkene python3, python3-pyyaml, podman, gnupg2 (gpgv),
policycoreutils-python-utils, acl og util-linux allerede installert. Kontoen
`produser` finnes fra før, og kjører ikke noe annet produkt.

```sh
# Sett fapolicyd sin subjektcache (README, avsnitt om fapolicyd) og restart.
sudo grep -q '^subj_cache_size = 16381$' /etc/fapolicyd/fapolicyd.conf \
    || echo 'Sett subj_cache_size = 16381 og kjør: sudo systemctl restart fapolicyd'
# Innleveringsområde for arkivene, utenfor hjemmekatalogen.
sudo install -d -o root -g root -m 0700 /var/tmp/sms-inn
# Kopier hit: sms-platform-1.4.2-offline.tar.gz(.sha256,.asc) og sms-sts-2.0.1-...
sudo sh -c 'cd /var/tmp/sms-inn && sha256sum -c sms-platform-1.4.2-offline.tar.gz.sha256 sms-sts-2.0.1-offline.tar.gz.sha256'
```

Suksess: begge linjer viser `OK`. Sjekksummer avdekker bare overføringsfeil;
signaturen under er det som autoriserer installasjon.

**Signeringspolicy:** produksjon krever signerte bundles og en offentlig nøkkel
som er levert og sjekksumverifisert gjennom en egen, betrodd kanal.
`release.py` nekter usignerte arkiver. For test brukes samme flyt med egne
testbundles signert med en egen testnøkkel (`BUNDLE_SIGNING_KEY` ved bygging);
det finnes ingen usignert snarvei, og ingen kode fra et arkiv kjøres før det er
verifisert.

Release-verktøyet installeres én gang etter README,
[First production installation](../README.md#first-production-installation)
(beskyttet kopi i `/usr/local/libexec`, verifisert mot uavhengig SHA256):

```sh
release_tool() {
    gzip -dc /usr/local/libexec/podman-offline-release.py.gz | sudo python3 -I -B - "$@"
}
# Én gang per produkt: den betrodde offentlige nøkkelen og dens uavhengige SHA256.
release_tool provision-key --product sms --keyring /var/tmp/sms-inn/bundle-signing.gpg \
    --key-sha256 "$nokkel_sha256"
# For hver release (også ved oppgradering): verifiser, publiser, fapolicyd-trust.
release_tool prepare --product sms --component platform --version 1.4.2 \
    --archive /var/tmp/sms-inn/sms-platform-1.4.2-offline.tar.gz \
    --signature /var/tmp/sms-inn/sms-platform-1.4.2-offline.tar.gz.asc
```

Suksess: siste linje er `PASS: protected release prepare`, og
`/var/lib/sms/releases/sms-platform-1.4.2/` finnes.

## 2. Administrator: klargjør verten (én gang)

```sh
sudo bash /var/lib/sms/releases/sms-platform-1.4.2/scripts/prepare-host.sh \
    --port 8443 --user produser
```

Skriptet endrer ikke kontoens hjem, shell eller pålogging. Det oppretter
`state/`, `config/` og `storage/` under `/var/lib/sms`, beholder eksisterende
subuid/subgid (legger til et område bare når det mangler), setter SELinux-
ekvivalens for lagringen, linger, port 8443 og drop-in-filen for brukersystemd.
Skriptet leser deretter miljøet til brukersystemd og starter eller restarter
den til den faktisk har verdiene; ellers stopper det med feil. En gjentakelse
fullfører derfor også en avbrutt kjøring. Suksess: to linjer
som begynner med `[OK]`. Steget kan gjentas trygt; det trengs på nytt bare ved
ny port. En annen eksisterende drop-in, et annet produkt på samme konto eller
en gammel installasjon med hjem i `/var/lib/sms` stoppes med en feilmelding.

## 3. Driftsbruker: installasjonsinnstillinger (én gang)

Logg inn som `produser` (ssh), eller `sudo -iu produser` og deretter
`export XDG_RUNTIME_DIR=/run/user/$(id -u)`.

```sh
install -d -m 0700 ~/.sms
printf 'INSTALL_ROOT=/var/lib/sms\n' > ~/.sms/sms.env
chmod 0600 ~/.sms/sms.env
```

Formatet er `NØKKEL=verdi`, én per linje, `#`-kommentarer og tomme linjer
tillatt; ett par omsluttende `'` eller `"` fjernes. Filen leses som data og kjøres
aldri som shell; `$(...)` og backticks utføres ikke. `INSTALL_ROOT` er påkrevd og
må være `/var/lib/<produkt>`. Andre nøkler (for eksempel eksisterende
applikasjonsinnstillinger) ignoreres, logges ikke og sendes ikke til containere.
Manglende fil, feil eierskap/modus, symlenker eller ugyldige linjer stopper før
noe skrives, med linjenummer men uten verdi. Ingen `HOME`-endring eller
terminaleksport trengs.

## 4. Driftsbruker: platform

```sh
cd /var/lib/sms/releases/sms-platform-1.4.2
bash ./deploy init-config platform
vi /var/lib/sms/state/platform/config.yaml
#   PUBLIC_ORIGIN: https://sms.example.org:8443
#   HTTPS_PORT: 8443
#   IP_ADDRESS: <serverens adresse>
install -d -m 0700 /var/lib/sms/state/platform/credentials/web
install -m 0600 /sti/til/web.crt /sti/til/web.key /var/lib/sms/state/platform/credentials/web/
bash ./deploy validate
bash ./deploy install
```

Suksess: `validate` skriver `[OK] validated platform; nothing written, ...`, og
`install` slutter med `podman ps`-listen der alle containere er `Up` (install
venter selv til de er healthy). Websertifikatet må dekke vertsnavnet i
`PUBLIC_ORIGIN`. Ikke kopier dev-credentials eller `config.dev.yaml`.

## 5. Administrator og driftsbruker: STS

Administrator publiserer STS-releasen som i steg 1 (`--component sts --version
2.0.1`). Deretter, som `produser`:

```sh
cd /var/lib/sms/releases/sms-sts-2.0.1
bash ./deploy init-config sts
vi /var/lib/sms/state/sts/config.yaml
```

`init-config` tar `PUBLIC_ORIGIN`, `HTTPS_PORT` og platforms delte verdier fra
installert platform. Velg produksjonens migrerings-/seed-filer og andre
STS-spesifikke innstillinger i denne filen; navn på secrets og credentials
følger STS sin egen config. Databasepassordet opprettes ved første install når
config-en deklarerer `generate: [password]`; et eksisterende passord beholdes
byte for byte. Signerings-PFX klargjøres i STS sin credentials-katalog etter
[PFX-veiledningen](PFX-CREDENTIALS.md) med `--root /var/lib/sms/state` og
`--component sts` (passordfilen `credentials/signing/pfx-password` først, `0600`).

**Sertifikatverktøyet på lukket nett:** `generate-certificates.sh` ligger ikke i
bundlene (pakket levering er backlog 45b). Administrator tar
`dev/generate-certificates.sh` fra samme gjennomgåtte kildecommit som bundlene,
overfører den sammen med arkivene og verifiserer SHA256 mot en verdi levert
gjennom den betrodde kanalen. Lagre den root-eid og lesbar, for eksempel
`/usr/local/libexec/podman-offline-generate-certificates.sh` (`0644`). Den kjøres
aldri som installert program, bare via stdin som `produser`, slik
PFX-veiledningen viser:

```sh
sha256sum /usr/local/libexec/podman-offline-generate-certificates.sh   # sammenlign med betrodd verdi
bash -s -- --root /var/lib/sms/state --cert-days 365 \
    --component sts --purpose signing --pfx \
    < /usr/local/libexec/podman-offline-generate-certificates.sh
```

Har organisasjonen allerede PFX eller `.crt`/`.key` for STS, eller `web.crt`/`web.key`
for platform, legges de i credentials-katalogen før kommandoen; verktøyet
beholder dem uendret og lager bare det som mangler (se PFX-veiledningen).

```sh
bash ./deploy validate
bash ./deploy install
```

Suksess som for platform. Installer eventuelle andre deklarerte avhengigheter
i den rekkefølgen `bundles.yaml` krever; `install` nekter en manglende avhengighet.

## 6. Driftsbruker: drift og kontroll

```sh
systemctl --user status sms-platform.service sms-sts.service
journalctl --user -u sms-sts.service --since -1h
# Podman-diagnostikk med produksjonens lagring (samme verdier som brukersystemd):
sms_podman() { XDG_CONFIG_HOME=/var/lib/sms/config XDG_DATA_HOME=/var/lib/sms/storage podman "$@"; }
sms_podman ps --all --pod
curl --cacert /sti/til/ca.crt https://sms.example.org:8443/livez
curl --cacert /sti/til/ca.crt -o /dev/null -w '%{http_code}\n' https://sms.example.org:8443/sts/
systemctl --user restart sms-sts.service && systemctl --user is-active sms-sts.service
```

Suksess: tjenestene er `active (running)`, containerne `Up (healthy)`, `/livez`
svarer og STS-siden gir forventet statuskode; test også innlogging i nettleser
mot det eksterne navnet. `sms_podman` er en lokal shellfunksjon for diagnostikk,
ikke en global eksport; uten den viser `podman` kontoens vanlige, tomme lagring.

Logg ut og la administrator kjøre `sudo reboot`. Etter oppstart, uten å logge inn:

```sh
sudo systemctl --user -M produser@ is-active sms-platform.service sms-sts.service
```

Suksess: `active` for begge. Kontroller deretter som `produser` at riktig lagring
og Quadlets brukes, og at produktet ikke har skrevet til hjemmekatalogen:

```sh
systemctl --user show-environment | grep '^XDG_'      # /var/lib/sms/config og /var/lib/sms/storage
systemctl --user show -p SourcePath sms-sts.service   # /var/lib/sms/config/containers/systemd/sms-sts.kube
sms_podman info --format '{{.Store.GraphRoot}}'        # /var/lib/sms/storage/containers/storage
find ~ -newer ~/.sms/sms.env                            # ingen produktfiler
```

## 7. Oppgradering og retry

Administrator publiserer den nye releasen (steg 1). `produser` kjører
`bash ./deploy validate` og `bash ./deploy install` fra den nye release-katalogen; config og
credentials i `state/` beholdes. Etter helse- og funksjonskontroll pensjonerer
administrator den gamle:

```sh
release_tool retire --product sms --component sts --version 2.0.2 --old-version 2.0.1
```

Feiler `install`, rett årsaken og kjør samme `bash ./deploy install` igjen; den
fullfører registrert gjenstående arbeid. Ikke rediger
`state/pending-operation.json`. Vanlig `bash ./deploy uninstall` beholder config,
credentials og databasevolumer; `--delete-data` sletter bare komponentens egne.

## Feilsøking

| Symptom | Kontroll | Tiltak |
| --- | --- | --- |
| `Missing ~/.sms/sms.env` eller modusfeil | `ls -la ~/.sms` | Opprett etter steg 3 (`0700`/`0600`, eid av produser) |
| `The user systemd manager has XDG_...` | `systemctl --user show-environment` | Administrator kjører steg 2 igjen |
| `/var/lib/sms/... must be ...` | `ls -ld /var/lib/sms /var/lib/sms/*` | Administrator kjører steg 2; ikke chmod/chown hele treet |
| Tjeneste finnes ikke etter install/reboot | `systemctl --user show -p SourcePath sms-sts.service` | Skal peke inn i `/var/lib/sms/config/...`; kontroller drop-in-filen |
| Manglende credentials | `bash ./deploy validate` | Feilen navngir config-fil og nøkkel, aldri verdien |
| `203/EXEC` eller fapolicyd-avvisning | `sudo ausearch -m FANOTIFY,AVC -ts recent`, `release_tool wait --product sms --component sts --version 2.0.1` | Kontroller `subj_cache_size` og at releasen er publisert med `prepare` |
| Images/volumer «forsvinner» | `sms_podman info --format '{{.Store.GraphRoot}}'` | Vanlig `podman` uten `sms_podman` ser kontoens hjemmelagring |

Detaljer om autentisering, fapolicyd-trust, SELinux og retry står i
[README](../README.md#first-production-installation). Design og tillitsgrenser
står i `ARCHITECTURE.md` (avsnittet «Production paths outside the login home»)
i kildekoden.
Gamle installasjoner med hjem i `/var/lib/<produkt>` migreres ikke.
