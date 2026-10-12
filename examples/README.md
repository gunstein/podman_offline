# Podman-eksempler

Kjør fra repo-roten. Python 3.6+, PyYAML, Bash, Podman og `sha256sum`
må finnes; `basic` trenger også `curl`. Kjør som vanlig bruker for rootless.
Eksemplene bruker `prepare`, ikke prod-installasjonen eller systemd.

## Oppsett på en maskin med nett

```sh
podman pull docker.io/library/busybox:1.37.0
podman tag docker.io/library/busybox:1.37.0 localhost/offline-example:1
podman image exists localhost/offline-example:1
```

Alle containere, også init-containerne, bruker dette lokale navnet og
`imagePullPolicy: Never`. Podman kan i tillegg trenge sitt infra/pause-image
ved første kjøring, avhengig av versjon og lokal konfigurasjon. Gjør første
prøvekjøring mens maskinen har nett. Eksemplene endrer ikke produktets manifester.
For å flytte testimaget til en maskin uten nett kan du bruke `podman save` og
`podman load`; dette er separat fra produktets bundle.

## Kjøring

```sh
./examples/run.sh basic
./examples/run.sh secrets
./examples/run.sh volumes
./examples/run.sh init-containers
./examples/run.sh manifest-defined
./examples/run.sh failures
```

`basic` bruker HTTP på `127.0.0.1:18080`. Overstyr ved behov:

```sh
EXAMPLE_PORT=18081 ./examples/run.sh basic
```

| Eksempel | Kontroller |
| --- | --- |
| [basic](basic/README.md) | ConfigMap/envFrom, typer i placeholders, HTTP og portbinding |
| [secrets](secrets/README.md) | Flere id-er, binære bytes, SHA-256 og utvalg/omdøping med `items` |
| [volumes](volumes/README.md) | Filtre, eiere/rettigheter, persistens og ny import |
| [init-containers](init-containers/README.md) | To init-containere i rekkefølge før appen |
| [manifest-defined](manifest-defined/README.md) | Manifestdefinert PVC og Secret/stringData/secretKeyRef |
| [failures](failures/README.md) | Fire forventede valideringsfeil, uten Podman |

Scriptet kopierer `deploy`, `deploy.py`, `images/`, `quadlet/`, eksempelets
config, manifester og eventuelle filer til en privat, midlertidig katalog.
Der erstattes markøren `example-run` med et unikt navn, og `POD_NAME` legges
til i config. Originalene endres ikke. Binærdata og den store negative
testfilen genereres bare i tempområdet; ingen nøkler eller sertifikater trengs.

Deretter kjøres `./deploy prepare`, `podman kube play --replace` og eksplisitte
kontroller med `podman exec` og eventuelt `curl`. Feil gir exit ulik 0.
Exit-trap kjører `podman kube down` og fjerner bare denne kjøringens PVC-volumer,
Secret-volumer og eventuelle gjenstående Secrets. Volumtesten beholder volumet
mellom sine to kjøringer, og fjerner det først ved endelig opprydding.
Testimaget beholdes for neste kjøring. SIGKILL/strømbrudd kan avbryte trapen.

Se [testresultater](RESULTS.md) og [manuell VM-sjekkliste](VM-CHECKLIST.md).
Podmans støtte varierer mellom versjoner; kjør eksemplene på samme versjon
som i målnettet. Feltene er beskrevet i
[Podmans kube play-dokumentasjon](https://docs.podman.io/en/v5.7.0/markdown/podman-kube-play.1.html).
