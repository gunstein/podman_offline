# volumes

Kjør `./examples/run.sh volumes` etter [image-oppsettet](../README.md).

Tester en `VOLUME_FILES`-id med en separat fil og et katalogtre. Katalogens
innhold skal ligge direkte i `/data`, uten en ekstra `tree/`-katalog.
SHA-256 kontrolleres for samtlige opplastede filer. Fra containeren skal
filen eies av `0:0` med 0644, katalogen av `0:0` med 0755, og det kjørbare
scriptet av `0:0` med 0755. Ved rootless viser dette eiere i containerens
brukernavnerom, ikke vertens numeriske bruker-ID-er.

Deretter skriver appen `/data/app-created.txt` og overskriver `/data/single.txt`.
Scriptet kjører `kube down` uten å fjerne volumet, endrer den opplastede
kildefilen, kjører `prepare` igjen og spiller YAML-en på nytt.

Forventet: appens egen fil er bevart, mens `single.txt` er lik den nye
opplastede filen. Hvis Podman-versjonen ikke importerer over et eksisterende
volum, vil siste SHA-256-kontroll feile og scriptet returnere ulik 0.
Volumet slettes etter testen, også ved verifikasjonsfeil.
