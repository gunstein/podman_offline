# secrets

Kjør `./examples/run.sh secrets` etter [image-oppsettet](../README.md).

Tester tre `SECRET_FILES`-id-er: en katalog med to tekstfiler, en binærfil og
en egen Secret fra samme tekstkatalog for å teste utvalg med `items`.
Binærfilen genereres ved kjøring med alle byteverdier 0–255, NUL, 0xff og CR/LF.
Alle mounts er read-only:

- `/inputs/text`: uten `items`, begge tekstfilene monteres med opprinnelig navn.
- `/inputs/binary`: eksplisitt `items` med `key: binary.bin` og `path: binary.bin`,
  tilsvarende mønsteret for en enkelt PFX-fil.
- `/inputs/selected`: `items` velger bare `message.txt` og plasserer den som
  `renamed.txt`. Den andre nøkkelen, `second.txt`, skal ikke monteres,
  og `message.txt` skal ikke finnes under sitt opprinnelige navn i dette mountet.

Forventet: SHA-256 fra hver fil på verten er lik SHA-256 lest med `podman exec`
fra containeren, også for filen med endret navn. Ikke-valgte nøkler skal mangle.
Ingen konvertering av binærdata tillates. Alle kontroller
passerer og scriptet returnerer 0. Secrets og deres navngitte mount-volumer
fjernes ved opprydding.

Testet med rootless Podman 5.7.0: samme filnavn i `key`/`path`, omdøping på
toppnivå og filtrering av ikke-valgte nøkler fungerer. SHA-256-kontrollene passerer.
En separat prøve med `path: nested/renamed.txt` feilet ved `kube play` med
exit 125 og meldingen `must not contain path separator`. Bruk derfor et filnavn
uten `/` i `items.path` på denne versjonen; katalogen velges med `mountPath`.
