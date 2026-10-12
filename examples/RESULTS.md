# Testresultater, 2026-10-12

Arbeidsmiljø: Podman **5.7.0**, **rootless** (`podman info` rapporterte `true`),
BusyBox **1.37.0**, lokalt tagget `localhost/offline-example:1`.
Ingen rootful-installasjon, systemd-operasjoner eller reboot ble utført.

| Kjøring | Resultat |
| --- | --- |
| `./examples/run.sh basic` | Exit 0: miljø, HTTP-svar og eksakt loopback-portbinding stemte |
| `./examples/run.sh secrets` | Exit 0: SHA-256 stemte også med `items`; samme filnavn, omdøping på toppnivå og utelating av ikke-valgte nøkler fungerte |
| `./examples/run.sh volumes` | Exit 0: innhold, eiere/rettigheter, appdata etter down/play og overskriving fra nytt arkiv stemte |
| `./examples/run.sh init-containers` | Exit 0: hovedcontaineren observerte `first`, deretter `second` |
| `./examples/run.sh manifest-defined` | Exit 0: PVC og Secret/stringData/secretKeyRef fungerte |
| `./examples/run.sh failures` | Exit 0: alle fire forventede prepare-feil ble kontrollert; ingen YAML/arkiver ble skrevet |

**Avvik fra en helt ren Podman-kjøring:** Ved `kube down` skrev Podman
`rootless netns: kill network process: permission denied` under en
`Error: stopping container ... network`-melding. Podman returnerte likevel 0.
Dette skjedde i de fem positive eksemplene, også mellom volumtestens to play.
Alle funksjonskontroller passerte. Etter kjøring viste separate lister ingen
av testenes containere, pods, secrets eller volumer. Nettverksprosessens
livssyklus er ikke verifisert utover dette, og årsaken er ikke fastslått.
Avviket må undersøkes dersom det gjentas på mål-VM-en.

Første versjon av runneren etterlot Secret-mount-volumer. Runneren ble rettet
til å fjerne også disse navngitte volumene, de første testvolumene ble fjernet,
og alle seks eksemplene ble kjørt på nytt med resultatene i tabellen.
Appenes PID 1 håndterer SIGTERM for å unngå unødvendig ti sekunders stopptimeout.

Oppfølging med `secret.items`: eksempelet beholder ett mount uten `items`, bruker
eksplisitt `key: binary.bin` / `path: binary.bin` for binærfilen og har en tredje
Secret som velger bare `message.txt` under navnet `renamed.txt`. Filhashene stemte,
og både det opprinnelige filnavnet og den utelatte nøkkelen `second.txt` manglet
i det filtrerte mountet. Den utvidede testen returnerte 0 på rootless Podman 5.7.0.

En prøve med `items.path: nested/renamed.txt` **feilet** med exit 125:
`name "nested/renamed.txt" must not contain path separator`. Underkataloger i
`items.path` er dermed ikke støttet i denne prøven. Det er en Podman-begrensning;
`deploy prepare` rendret manifestet uten feil. Den vanlige eksempelkjøringen
bruker derfor omdøping på toppnivå. Begge kjøringene ryddet opp egne ressurser;
den vellykkede kjøringen hadde fortsatt nettverksavviket beskrevet over.

## Enhetstester og kvalitetskontroller

- 51 nye tester: 42 deploy-tester og 9 bundle-tester, med ytterligere varianter
  i `subTest`.
- Python 3.14.4 / PyYAML 6.0.3: alle 51 passerer.
- Python 3.11.17 / PyYAML 5.4.1 (`.venv54`): alle 51 passerer.
- Ruff 0.17.0: lint og formatkontroll rene.
- Pyright 1.1.414: 0 feil og 0 advarsler.
- Vermin 1.8.0: minstekrav Python 3.6, target `3.6-` godkjent.
- `bash -n examples/run.sh`: godkjent.

De oppgitte 21 originaltestene og flere originalfiler fantes ikke i arbeidsområdet.
De kunne derfor ikke leses eller kjøres. Nye tester ligger i separate filer;
ingen originaltester er erstattet. Testene på 5.4.1/6.x og den statiske
kompatibilitetskontrollen er ikke det samme som en faktisk kjøring på Python 3.6.

## Python-koden og åpne observasjoner

Ved denne eksempelkjøringen var `deploy.py` og `bundle.py` uendret. Ingen av de implementerte testene eller
Podman-eksemplene avdekket en Python-feil som krevde retting, og det er derfor
ingen feilrettingscommit.

Følgende begrensninger er observert ved lesing, uten endring av eksisterende
oppførsel:

- Koblingssjekken validerer Secret/PVC-navn, ikke om `secretKeyRef.key` finnes
  eller hele Kubernetes/Podman-skjemaet. De ekte eksemplene utfyller dette.
- Filarkiver skrives først etter vellykket validering, men skriving av flere
  arkiver er ikke en atomisk transaksjon ved for eksempel diskfeil.
- Volumimport overskriver opplastede filer ved neste play. Det er tilsiktet
  oppførsel; appdata som skal beholdes bør ha andre filnavn eller eget volum.

Produksjonsoppstart og faktisk reboot må kontrolleres manuelt med
[VM-sjekklisten](VM-CHECKLIST.md) og en komplett bundle.

Senere er image-håndteringen endret til strukturell YAML-lesing og ett felles
image-arkiv. Gjeldende bygg- og installasjonsflyt er beskrevet i
[README](../README.md#offline-bundle-og-rootful-quadlet).
