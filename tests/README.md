# Enhetstester

`test_deploy.py` og `test_bundle.py` bruker bare standardbiblioteket
og PyYAML. Alle stier peker inn i `TemporaryDirectory`; subprocess og root-sjekk
stubbes. Ingen nettverk, Podman, systemd eller root kreves. Bundle-testene skriver
og leser ekte tar-arkiver og verifiserer alle SHA-256-linjene, men stubber image-save.

```sh
python3 -m unittest discover -s tests
.venv54/bin/python -m unittest discover -s tests
ruff check deploy.py bundle.py tests/
ruff format --check deploy.py bundle.py tests/
pyright deploy.py bundle.py tests/
vermin -t=3.6- deploy.py bundle.py tests/
```

For PyYAML 5.4.1 brukes en Python-versjon som den kan bygges på (testet med 3.11):

```sh
python3.11 -m venv .venv54
.venv54/bin/pip install setuptools wheel 'cython<3'
.venv54/bin/pip install --no-build-isolation pyyaml==5.4.1
```

Lint/type/vermin er utviklingsverktøy, ikke nye runtime-avhengigheter.
Testene bruker Python 3.6-kompatibel syntaks og standardbibliotek-API-er.
Originalfilen `tests/test_deploy.py` med 21 tester fantes ikke i det leverte
arbeidsområdet. Ved omorganiseringen fikk de nye testfilene navnene ovenfor;
ingen originaltester ble overskrevet. Eventuelle originaltester må legges til
uten å overskrive de nye testene.

## Images fra manifestene

65 tester passerer med PyYAML 6.0.3 (Python 3.14.4) og 5.4.1 (Python 3.11.17).
Image-testene dekker Pod/Deployment, init-containere, flere filer/dokumenter,
flow-maps, duplikater, fulle navn og forventede valideringsfeil. Bundle-testene
kontrollerer én sortert multi-image-save, navnelisten, tar-innhold og checksums.
Installer-testene kontrollerer render/load/exists-rekkefølgen, rendrede navn,
manglende arkiv/image og at eksisterende Quadlet-filer bevares ved kontrollfeil.
Prepare-testene kjører fortsatt helt uten Podman-kall.

Ekte save/load ble verifisert 2026-10-12 med **Podman 5.7.0, rootless**.
Tre eksisterende navn ble lagret med `podman save -m -o images.tar ...` og lastet
med `podman load -i images.tar` i et tomt, midlertidig VFS-image-lager
(`--root`, `--runroot`, `--storage-driver vfs`). Alle tre
`podman image exists`-kontrollene returnerte 0. `podman images` etter load viste:

```text
docker.io/library/nginx:1.28-alpine dc73b49f5124
localhost/offline-example:1 30ecbe150909
docker.io/library/busybox:1.37.0 30ecbe150909
```

Fulle navn og tagger ble bevart, også to navn for samme image-ID.
Testlageret ble fjernet etterpå. Dette var en separat save/load-test med små
testimages; full produktbundle og rootful Quadlet-installasjon ble ikke kjørt
som del av denne endringen.

Review-regresjoner dekker navnekollisjoner mellom Secret/PVC/ConfigMap,
validering uten arkivskriving, bevaring av gamle arkiver ved load/exists-feil,
installasjon av network-Quadlet før daemon-reload og avvisning av dupliserte
manifestnøkler under bygging. Testene for kollisjoner, arkivbevaring og
dupliserte nøkler feilet før rettingene.

Review-rettingene ble også prøvd med ekte rootless Podman 5.7.0:
backendens vertsprosess fikk SIGKILL, restart-telleren gikk fra 0 til 1 og
HTTP-ende-til-ende-testen passerte etter automatisk restart. Begge private nøklene
i Secret-mountene (Duende-signering og nginx TLS) hadde mode 0400.
Den ekte Quadlet-generatorens dryrun viste myproduct-network.service,
network create --ignore og Requires/After fra hovedtjenesten.
Ved kube down kom fortsatt det tidligere dokumenterte rootless-netns-avviket,
men kommandoen returnerte 0 og ny oppstart fungerte.
Rootful systemd/reboot og database utilgjengelig i over 60 sekunder er fortsatt
manuelle VM-tester, ikke verifisert av denne kjøringen.
