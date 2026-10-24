# Produksjonsinstallasjon

For administrator/installatør med begrenset Linux-erfaring. Alle nødvendige
steg står her, i rekkefølge. Designforklaringer står i [README](../README.md).
**Status:** backlog 65 er under implementasjon. Fersk OL9-labkjøring og
menneskelig utprøving uten hjelp gjenstår; historiske tester godkjenner ikke
kommandoene nedenfor. Verifikasjonsrapporten heter `acceptance/HOST-SETUP.md` i kildekoden.

## Før du begynner

Du trenger en Oracle Linux 9-server med SELinux Enforcing, aktiv fapolicyd og
firewalld. Organisasjonens administrator leverer en eksisterende innloggingskonto
`produser` uten sudo, wheel, adm eller systemd-journal. Hjem og shell beholdes.
Python 3, python3-pyyaml, Podman, gnupg2, fapolicyd, firewalld,
policycoreutils-python-utils, acl, util-linux, shadow-utils og sudo skal være
installert fra organisasjonens godkjente offline-repository. `setup` kontrollerer
kommandoene og gir pakkenavn hvis noe mangler. Ingen kommando laster ned pakker.

**To kontoer:** Administratoren bruker sudo for klargjøring, publisering og
pensjonering av releaser. Driftsbrukeren logger inn selv med SSH og bruker aldri
sudo. Produktfiler legges under `/var/lib/myproduct`; i hjemmet opprettes bare
`~/.myproduct/myproduct.env`. SSH-nøkler tilhører den vanlige innloggingen.

Bestill følgende levering fra leverandøren før endringer på serveren:

- Denne manualen fra en betrodd kilde, `release.py.gz`, `bundle-signing.gpg`,
  valgte `<produkt>-<komponent>-<versjon>-offline.tar.gz` og tilhørende `.asc`.
  Signatur er obligatorisk; `.sha256` kan følge med for overføringskontroll.
- **To SHA256-verdier via en separat, autentisert kanal:** for `release.py.gz`
  og `bundle-signing.gpg`. En sjekksumfil ved siden av opplastingen er ikke nok.
- For eksempelet med platform og identity: `web.crt`, `web.key`, `identity.crt`,
  `identity.key`, `alice-password`, `bob-password` og offentlig `ca.crt`.
  Websertifikatet skal dekke vertsnavnet i `public_origin`. Disse filene leveres
  privat til driftsbrukeren. De to passordfilene gjelder demoens brukere;
  organisasjonens komponenter må ha sin egen leveringsliste. PFX-varianten
  trenger i stedet `signing-cert.pfx` og den private enlinjesfilen `pfx-password`.

Be administratoren klargjøre server/konto dersom disse forutsetningene mangler.
Ikke opprett credentials fra dev eller bruk et usignert arkiv som snarvei.
For leverandøren: `gzip -n -c scripts/release.py > release.py.gz` lages fra samme
separat gjennomgåtte kildecommit som verktøyet skal representere. Produser ikke
verktøyet fra et uverifisert bundle.

### Verdier du bytter ut én gang

Kopier blokken under til terminalen på hver maskin/ny innlogging der du følger
stegene. Bytt **bare verdiene mellom apostrofene** etter tabellen. Dette er
offentlige innstillinger; legg aldri passord eller private nøkler i blokken.
Ikke bruk apostrof eller linjeskift inne i en verdi. Versjonene hentes fra
leveringens filnavn; de behøver ikke være like.

| Verdi | Betyr |
| --- | --- |
| `server`, `admin`, `runtime` | serveradresse og de to innloggingskontoene |
| `product` | leverandørens produktnavn; `myproduct` i eksempelet |
| `gateway`, `login_component` | komponentnavn; eksempelets `platform` og `identity` |
| `gateway_version`, `login_version` | versjoner i leveringen, ikke en antakelse om siste versjon |
| `old_gateway_version` | tidligere installert gateway-versjon, bare brukt ved pensjonering etter oppgradering |
| `port`, `public_origin`, `bind_ip` | samme HTTPS-port og serveradresse som tjenesten skal bruke |
| `upload` | innleveringskatalog på serveren, utenfor hjemmet |
| `credentials` | driftsbrukerens private innleveringskatalog på serveren |
| `helper_sha256`, `key_sha256` | erstatt teksten med de to uavhengig mottatte 64-tegns verdiene |
| `credential_format` | `pem` for demoen; `pfx` bare for en levert komponent som deklarerer `credentials/signing/signing-cert.pfx` |
| `discovery_path` | leverandørens faktiske discovery-sti, som i eksempelet |
| `with_identity` | `yes` for eksempelet; `no` for bare gateway, uten Identity eller database |

<!-- operator: values -->
```sh
server='192.168.0.108'
admin='gunstein'
runtime='produser'
product='myproduct'
gateway='platform'
login_component='identity'
gateway_version='0.4.12'
old_gateway_version='0.4.11'
login_version='0.4.12'
port='8443'
public_origin='https://myproduct-proxy:8443'
bind_ip='192.168.0.108'
upload='/var/tmp/myproduct-upload'
credentials='/var/tmp/myproduct-credentials'
helper_sha256='BYTT_TIL_VERKTOYETS_UAVHENGIGE_SHA256'
key_sha256='BYTT_TIL_NOKKELENS_UAVHENGIGE_SHA256'
with_identity='yes'
credential_format='pem'
discovery_path='/identity/.well-known/openid-configuration'
```

## 1. Overfør levering

**Maskin:** laptop. **Bruker:** administratorens innlogging. Kjør verdiblokken,
og logg inn på serveren:

<!-- operator: admin-login -->
```sh
ssh "$admin@$server"
```

**Forventet:** serverens shellprompt. Kjør verdiblokken i den nye sesjonen også.

**Maskin:** server. **Bruker:** administrator, uten sudo i dette steget. Kjør
verdiblokken først. Opprett en privat katalog som du selv eier; ingen ekstra kopiering til en
root-only katalog er nødvendig.

<!-- operator: upload-directory -->
```sh
install -d -m 0700 "$upload"
```

**Maskin:** laptop. **Bruker:** administrator. Kjør verdiblokken her også og stå
i katalogen med den mottatte offentlige leveringen. Private credentialfiler
kopieres senere med driftsbrukerens konto.

<!-- operator: transfer -->
```sh
(
set -eu
scp release.py.gz bundle-signing.gpg "$product-$gateway-$gateway_version-offline.tar.gz" "$product-$gateway-$gateway_version-offline.tar.gz.asc" "$admin@$server:$upload/"
if [ "$with_identity" = yes ]; then
  scp "$product-$login_component-$login_version-offline.tar.gz" "$product-$login_component-$login_version-offline.tar.gz.asc" "$admin@$server:$upload/"
fi
)
```

**Forventet:** scp fullfører uten feil. Mangler en fil: hent den fra leverandøren,
kjør samme overføring igjen, og fortsett med steg 2.

## 2. Installer betrodd verktøy

**Maskin:** server. **Bruker:** administrator med sudo. Kjør verdiblokken ved
ny innlogging. Kopier hele blokken. Den kontrollerer den uavhengige sjekksummen
på en beskyttet kopi før verktøyet kan kjøres. En eldre kopi beholdes ved feil.
Du skal ikke redigere Python-koden. Steget kan gjentas med samme leveranse.

<!-- operator: tool-bootstrap -->
```sh
sudo python3 -I -B - "$upload/release.py.gz" "$helper_sha256" <<'PY'
import errno, hashlib, os, stat, sys, tempfile
from pathlib import Path

def protected(path, directory):
    info = path.lstat()
    if info.st_uid != 0 or info.st_mode & 0o022 or not (
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    ):
        raise ValueError('Unsafe protected path; ask administrator to inspect: ' + str(path))
    for key in ('system.posix_acl_access', 'system.posix_acl_default'):
        try:
            os.getxattr(str(path), key, follow_symlinks=False)
        except OSError as error:
            if error.errno not in (errno.ENODATA, errno.ENOTSUP):
                raise
        else:
            raise ValueError('ACL on protected path; ask administrator to inspect: ' + str(path))

source, expected = sys.argv[1:]
target = Path('/usr/local/libexec/podman-offline-release.py.gz')
if os.geteuid() != 0 or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
    raise SystemExit('ERROR: administrator access and independent SHA256 required; repeat bootstrap with correct inputs')
temporary = None
try:
    for parent in reversed((target.parent,) + tuple(target.parent.parents)):
        if not os.path.lexists(str(parent)):
            parent.mkdir(mode=0o755)
        protected(parent, True)
    if os.path.lexists(str(target)):
        protected(target, False)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as incoming:
        if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
            raise ValueError('Helper upload must be a regular file')
        with tempfile.NamedTemporaryFile(dir=str(target.parent), prefix='.bootstrap-', delete=False) as out:
            temporary = Path(out.name)
            value = hashlib.sha256()
            for block in iter(lambda: incoming.read(1024 * 1024), b''):
                value.update(block)
                out.write(block)
            if value.hexdigest() != expected:
                raise ValueError('Helper SHA256 mismatch; obtain correct file/digest, then repeat bootstrap')
            out.flush()
            os.fchmod(out.fileno(), 0o644)
            os.fsync(out.fileno())
    os.replace(str(temporary), str(target))
    fd = os.open(str(target.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print('PASS: authenticated release tool installed; continue with setup')
except (OSError, ValueError) as error:
    if isinstance(error, ValueError):
        raise SystemExit('ERROR: ' + str(error)) from None
    raise SystemExit('ERROR: bootstrap I/O failure; administrator must inspect upload/target permissions and space, then repeat bootstrap') from None
finally:
    if temporary is not None and temporary.exists():
        temporary.unlink()
PY
```

**Forventet:** `PASS: authenticated release tool installed`.
Ved SHA256-feil: be om korrekt verktøy/verdier gjennom den betrodde kanalen,
oppdater verdiblokken og gjenta steg 2. Ved eierskaps-/ACL-feil må administratoren
undersøke den navngitte systemstien; ikke kjør rekursiv chmod/chown.

## 3. Klargjør server og valgte releaser

**Maskin:** server. **Bruker:** administrator med sudo. Kopier hele blokken.
Bare komponentene som er angitt her behandles. Andre filer i katalogen ignoreres.

<!-- operator: setup -->
```sh
(
set -euo pipefail
set -- --release "$gateway@$gateway_version"
if [ "$with_identity" = yes ]; then
  set -- "$@" --release "$login_component@$login_version"
fi
gzip -dc /usr/local/libexec/podman-offline-release.py.gz | sudo python3 -I -B - setup \
  --product "$product" --user "$runtime" --port "$port" \
  --input-dir "$upload" --keyring "$upload/bundle-signing.gpg" --key-sha256 "$key_sha256" \
  "$@" --host-release "$gateway@$gateway_version"
)
```

**Forventet:** `PASS: setup preflight`, én `PASS: release ready` per komponent og
sist `PASS: host setup`. Verktøyet viser neste kommando som driftsbrukeren skal
kjøre. Dette har publisert release og klargjort verten; appene er ennå ikke
installert. Det opprettes ingen installasjonskvittering på deres vegne.

Kommandoen kontrollerer OS, pakker, konto, sudo-policy, sikkerhetstjenester,
nøkkel, journalpolicy og plass før produktendringer. Arkivinnhold og utpakket
størrelse kan først valideres etter signaturkontroll. Feil i et senere bundle
kan derfor etterlate tidligere verifiserte releaser, men kjører ikke host-skriptet.
Plasskontrollene er nedre grenser med 1 GiB reserve per filsystem; administratoren
må i tillegg dimensjonere images og databaser. På standard OL9 opprettes
`/var/log/journal`, og journald tømmes til disk. Dette gjør **hele vertens** journal
vedvarende og krever plass under `/var/log`. Eksplisitt motstridende journalpolicy
overskrives ikke. Ingen ekstra grupper gis til driftsbrukeren.

### Hvis preflight stopper

**Samme maskin/administrator.** Følg den navngitte feilen, og kjør deretter hele
steg 3 på nytt. Ved manglende kommando: installer pakken feilen navngir fra
organisasjonens offline-repository. Ved sudo-grant: bruk en konto uten grants;
ikke gi produktet sudo. Ved `Storage`/`SplitMode`-konflikt må systemansvarlig
først godkjenne persistent journal med `Storage=auto` eller `persistent` og
`SplitMode=uid`; ikke omgå policyen med grupper.

For standard OL9 med for liten fapolicyd-cache, kontroller at innstillingen finnes
og bruk denne eksakte rettingen. Den endrer cache-størrelse, ikke tillitsregler.
Hvis første kommando feiler, stopp og be systemansvarlig klargjøre baseline.

<!-- operator: cache-remedy -->
```sh
if sudo grep -Eq '^[[:space:]]*subj_cache_size[[:space:]]*=' /etc/fapolicyd/fapolicyd.conf; then
  sudo sed -i -E 's/^[[:space:]]*subj_cache_size[[:space:]]*=.*/subj_cache_size = 16381/' /etc/fapolicyd/fapolicyd.conf &&
  sudo systemctl restart fapolicyd
else
  printf 'STOP: subj_cache_size mangler; systemansvarlig må klargjøre OL9-baseline før steg 3 gjentas.\n' >&2
  false
fi
```

**Forventet:** ingen feil. Kjør så steg 3 igjen. For annen preflight-feil følger du
rettingen som vises; ikke bruk cache-rettingen som generell reparasjon.

## 4. Logg inn som driftsbruker

**Maskin:** laptop. **Bruker:** driftsbrukerens innlogging, uten sudo.

<!-- operator: login -->
```sh
ssh "$runtime@$server"
```

**Maskin:** server i den nye SSH-sesjonen. **Bruker:** driftsbruker uten sudo.
Kjør verdiblokken igjen, og opprett produktets innstillingsfil:

<!-- operator: init-layout -->
```sh
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" init-layout
```

**Forventet:** `[OK] Bootstrap ready` eller `[OK] Existing bootstrap retained`.
Steget kan gjentas; eksisterende gyldige innstillinger beholdes. Ved konflikt:
be administratoren undersøke produkt-/kontotilknytningen og fortsett deretter
med samme kommando. Ikke slett eller overskriv en eksisterende innstillingsfil.
Ved avbrudd kjører du samme `init-layout`-kommando på nytt som driftsbruker.
En uferdig midlertidig fil tas ikke i bruk og hindrer ikke neste forsøk.

## 5. Konfigurasjon og private credentials

**Maskin:** server. **Bruker:** driftsbruker uten sudo. Initialiser gateway:

<!-- operator: gateway-config -->
```sh
(
set -eu
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" init-config "$gateway"
python3 - "$product" "$gateway" "$public_origin" "$port" "$bind_ip" <<'PY'
from pathlib import Path
import sys, yaml
product, component, origin, port, address = sys.argv[1:]
p = Path('/var/lib') / product / 'state' / component / 'config.yaml'
v = yaml.safe_load(p.read_text())
v.update(PUBLIC_ORIGIN=origin, HTTPS_PORT=int(port), IP_ADDRESS=address)
p.write_text(yaml.safe_dump(v))
print('OK: public gateway settings saved; continue with credentials')
PY
install -d -m 0700 "$credentials"
)
```

**Forventet:** init-config viser at config er opprettet eller beholdt, etterfulgt
av `OK: public gateway settings saved`. Innstillingene kommer fra verdiblokken.
Dette er et eksplisitt redigeringssteg: ved vanlig retry/oppgradering skal du
ikke kjøre redigeringssteget på nytt med gamle verdier.
Blokken stopper ved første feil. Hvis `init-config` feiler, blir eksisterende
config ikke redigert. Rett den oppgitte årsaken, kontroller verdiblokken og gjenta
denne blokken som driftsbruker på serveren før du går videre.

**Maskin:** laptop. **Bruker:** driftsbrukerens innlogging. Stå i katalogen med
private filer fra leverandøren. Kjør verdiblokken på laptopen først.

<!-- operator: credentials-transfer -->
```sh
(
set -eu
scp web.crt web.key ca.crt "$runtime@$server:$credentials/"
if [ "$with_identity" = yes ]; then
  case "$credential_format" in
    pem) scp identity.crt identity.key alice-password bob-password "$runtime@$server:$credentials/";;
    pfx) scp signing-cert.pfx pfx-password "$runtime@$server:$credentials/";;
    *) printf 'STOP: credential_format må være pem eller pfx fra leverandørens verdiliste.\n' >&2; false;;
  esac
fi
)
```

**Forventet:** ingen scp-feil. Bruk aldri chat, terminalutskrift eller Git til å
sende disse filene. Private filer skal være eiet av driftsbrukeren, modus 0600.
På **serveren som driftsbruker**, installer bare gateway-filer:

<!-- operator: gateway-credentials -->
```sh
(
set -e
install -d -m 0700 "/var/lib/$product/state/$gateway/credentials/web"
for name in web.crt web.key; do
  destination="/var/lib/$product/state/$gateway/credentials/web/$name"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    test ! -L "$destination" && cmp -s "$credentials/$name" "$destination" || { printf 'STOP: credentialkonflikt for %s; behold filen og kontakt credentialansvarlig, gjenta deretter dette steget.\n' "$name" >&2; exit 1; }
  else
    install -m 0600 "$credentials/$name" "$destination" || exit 1
  fi
done
)
```

**Forventet:** ingen feil; identiske eksisterende filer beholdes. Ved konflikt:
stopp og be credentialansvarlig avklare riktig sett. Ikke overskriv beholdte nøkler.

## 6. Installer og kontroller gateway

**Maskin:** server. **Bruker:** driftsbruker uten sudo.

<!-- operator: gateway-install -->
```sh
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" validate &&
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" install
```

**Forventet:** validated, deretter tjenesten healthy og containere Up. Ved feil:
følg «Feil og avbrudd» nedenfor og kjør samme blokk på nytt. Etter suksess:

<!-- operator: gateway-check -->
```sh
curl --cacert "$credentials/ca.crt" --resolve "$(printf '%s' "$public_origin" | sed -E 's@https://([^:/]+).*@\1@'):$port:$bind_ip" -sS -o /dev/null -w '%{http_code}\n' "$public_origin/livez"
```

**Forventet:** `204`. Curl kan ikke erstatte sertifikatkontroll med `-k`.
Hvis `with_identity=no`, hopp til steg 8. Gateway alene trenger ingen Identity,
database eller demobrukere.

## 7. Installer identity (når valgt)

**Maskin:** server. **Bruker:** driftsbruker uten sudo. Gateway skal allerede
være installert. Leverandøren velger credential-varianten i verdiblokken:

| Variant | Privat leveranse | Destinasjon under komponentens `credentials/` |
| --- | --- | --- |
| `pem` (demoen) | `identity.crt`, `identity.key`, `alice-password`, `bob-password` | sertifikat/nøkkel i `identity/`, demopassord i `users/` |
| `pfx` (egen levert Identity) | `signing-cert.pfx`, `pfx-password` | begge i `signing/`; komponentens leverte config skal allerede deklarere PFX-referansen |

Passordfilen har én ikke-tom linje. Skriv aldri passord som kommandolinjeargument.
Leverandøren må avklare om applikasjonen trenger passordet som en separat Secret;
provisioning-filer leveres aldri implicit. Ikke endre demoens PEM-config ved å
gjette PFX-innstillinger. Kopier den samme blokken for begge varianter:

<!-- operator: identity-config -->
```sh
(
set -e
bash "/var/lib/$product/releases/$product-$login_component-$login_version/deploy.sh" init-config "$login_component"
case "$credential_format" in
  pem) names='identity.crt identity.key alice-password bob-password';;
  pfx) names='signing-cert.pfx pfx-password';;
  *) printf 'STOP: credential_format må være pem eller pfx fra leverandørens verdiliste.\n' >&2; exit 1;;
esac
for name in $names; do
  case "$name" in
    signing-cert.pfx|pfx-password) group=signing;;
    *-password) group=users;;
    identity.*) group=identity;;
    *) group=signing;;
  esac
  install -d -m 0700 "/var/lib/$product/state/$login_component/credentials/$group"
  destination="/var/lib/$product/state/$login_component/credentials/$group/$name"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    test ! -L "$destination" && cmp -s "$credentials/$name" "$destination" || { printf 'STOP: credentialkonflikt for %s; behold filen og kontakt credentialansvarlig, gjenta deretter dette steget.\n' "$name" >&2; exit 1; }
  else
    install -m 0600 "$credentials/$name" "$destination" || exit 1
  fi
done
)
```

**Forventet:** initialisert eller beholdt config, ingen kopieringsfeil. Filer
beholdes ved gjentakelse. Databasepassord genereres av install hvis deklarert;
et eksisterende passord beholdes. Installer:

<!-- operator: identity-install -->
```sh
bash "/var/lib/$product/releases/$product-$login_component-$login_version/deploy.sh" validate &&
bash "/var/lib/$product/releases/$product-$login_component-$login_version/deploy.sh" install
```

**Forventet:** begge tjenester healthy. Kontroller med:

<!-- operator: identity-check -->
```sh
curl --cacert "$credentials/ca.crt" --resolve "$(printf '%s' "$public_origin" | sed -E 's@https://([^:/]+).*@\1@'):$port:$bind_ip" -sS -o /dev/null -w '%{http_code}\n' "$public_origin$discovery_path"
```

**Forventet:** `200`. Demoens `/identity/` er ikke en gyldig suksesskontroll
(gir 404). Leverandøren må oppgi det faktiske endepunktet for sin komponent.
Utstedelse/konvertering av egne sertifikater er en avansert leverandøroppgave,
beskrevet i [PFX-design og provisioning](PFX-CREDENTIALS.md).
`generate-certificates.sh` følger ikke med bundlene; ekstern PEM/PFX-levering
ovenfor trenger det ikke.

## 8. Drift, ny innlogging og omstart

**Maskin:** server. **Bruker:** driftsbruker uten sudo. Kjør verdiblokken igjen
etter hver ny innlogging. Alle stier er absolutte; ingen huskede shellfunksjoner
eller manuelle XDG-eksporter trengs.

<!-- operator: status -->
```sh
(
set -eu
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" status
systemctl --user is-active "$product-$gateway.service"
journalctl --user -u "$product-$gateway.service" -b -n 10 --no-pager --output=json --output-fields=__REALTIME_TIMESTAMP,_SYSTEMD_USER_UNIT,USER_UNIT,PRIORITY
)
```

**Forventet:** status viser complete/active og ingen pending, is-active viser
`active`, og journalen inneholder JSON-poster med tidsstempel og unitnavn.
Dette viser lesetilgang uten å skrive ut meldingsinnhold (`MESSAGE`). Ikke del rå journaltekst
med passord, tokens eller tilkoblingsstrenger; se trygge feilmeldinger nedenfor.

Logg ut som driftsbruker (`exit`). **Administrator på serveren med sudo**
kjører `sudo reboot`. Etter oppstart logger administratoren inn igjen og kjører
verdiblokken og kontrollen nedenfor **før driftsbrukeren logger inn**:

<!-- operator: boot-check -->
```sh
set -- "$product-$gateway.service"
if [ "$with_identity" = yes ]; then set -- "$@" "$product-$login_component.service"; fi
sudo systemctl --user -M "$runtime@" is-active "$@"
```

**Forventet:** `active` for hver valgt tjeneste. Logg deretter inn igjen som driftsbruker med steg 4,
kjør verdiblokken og steg 8. Forvent samme status og lesbar journal uten sudo.

## 9. Oppgradering og feil/avbrudd

Ved oppgradering: administratoren overfører den nye leveringen (steg 1), endrer
bare leverte versjoner i verdiblokken og kjører steg 3. Verktøyoppdatering krever
ny uavhengig verifisering i steg 2. Driftsbrukeren logger inn, bruker nye versjoner
i verdiblokken og kjører validate/install i steg 6/7. Hopp over redigering og
credentialkopiering; eksisterende config, nøkler og data beholdes.

Når funksjonskontrollene er grønne kan administratoren pensjonere en gammel
release. Kopier blokken på **serveren som administrator med sudo** etter å ha
satt `old_gateway_version` til versjonen som faktisk er erstattet:

```sh
(
set -euo pipefail
gzip -dc /usr/local/libexec/podman-offline-release.py.gz | sudo python3 -I -B - retire \
  --product "$product" --component "$gateway" --version "$gateway_version" --old-version "$old_gateway_version"
)
```

**Forventet:** `PASS: protected release retire`. Gamle releaser slettes aldri
som automatisk feilopprydding.

| Hendelse | Hva du gjør og kjører videre |
| --- | --- |
| Avbrutt bootstrap | Administrator kjører steg 2 igjen med samme betrodde SHA256. Ved feil beholdes gammel verktøykopi. |
| Avbrutt setup, signatur-/trustfeil | Administrator retter den navngitte fil-/baselinefeilen og kjører hele steg 3 igjen. Tidligere godkjente releaser beholdes; feil signatur autoriserer aldri kode. |
| Setup stopper etter journal/drop-in | Administrator kjører steg 3 igjen. Det kontrollerer faktisk manager/journal/firewall, ikke bare om filer finnes. |
| Ny SSH-sesjon | Kjør verdiblokken igjen. `init-layout` kan gjentas og beholder gyldig fil. |
| Install feiler | Driftsbruker kjører status fra steg 8; komponenten skal stå ufullført/pending. Rett navngitt config-/credentialfeil fra leveringens offentlige felt/filnavn, og kjør samme validate/install-blokk igjen. Ikke rediger pending-recorden. |
| Eksisterende credentials er forskjellige | Stopp kopieringen, behold filene og be credentialansvarlig avklare settet. Gjenta credentialsteget først når leveringen er korrekt. Ingen hemmelige verdier trenger deles. |
| Manglende journal eller manager-miljø | Administrator kjører steg 3 igjen. Ikke legg driftsbrukeren i privileged grupper eller eksporter XDG manuelt. |
| Uventet feil uten konkret retting | Stopp. Send bare stegnavn, offentlig komponent/versjon og fast feilmelding; ikke dump config, miljø, inspect eller journal. Leverandøren må gi en trygg retting og neste kommando før du fortsetter. |

Steg 2, 3, init-layout, init-config og identisk credentialkopiering kan gjentas.
Et install-forsøk er trygt å fullføre med samme kommando og beholdte innstillinger;
`upgrade: always` kan restarte den valgte tjenesten ved gjentakelse. Gjenta ikke
config-redigering med gamle verdier eller retirement av en annen versjon.
Kjør bare én setup/install/upgrade/retire-operasjon om gangen.
