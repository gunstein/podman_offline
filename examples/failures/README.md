# failures

Kjør `./examples/run.sh failures`. Krever Python og PyYAML, men ikke Podman
eller det lokale testimaget. Hvert undertilfelle har egen config og eget manifest.

| Tilfelle | Forventet feilmelding |
| --- | --- |
| `unused-id` | VOLUME_FILES-id-en «brukes ikke av noe manifest» |
| `unknown-claim` | PersistentVolumeClaim «finnes ikke» |
| `partial-placeholder` | «Uerstattet @@...@@» |
| `large-secret` | SECRET_FILES-id-en «er for stor» |

Den store filen genereres som 400 000 byte i tempområdet. For hver variant
må `./deploy prepare` feile, den forventede teksten må finnes i output, og
verken `build/install.yaml` eller `build/files` skal finnes. Scriptet selv
returnerer 0 bare når alle fire forventede feil er bekreftet; feil årsak eller
uventet vellykket rendring gir exit ulik 0.
