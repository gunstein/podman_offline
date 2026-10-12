# manifest-defined

Kjør `./examples/run.sh manifest-defined` etter [image-oppsettet](../README.md).

Både appdata-PVC-en og en Secret er definert direkte i manifestet, uten
`SECRET_FILES` eller `VOLUME_FILES`. Secret bruker `stringData` med en tydelig
syntetisk verdi. Containeren leser verdien via `env.valueFrom.secretKeyRef`
og skriver den til PVC-volumet.

Forventet: både miljøvariabelen `TOKEN` og filen `/data/token-seen` inneholder
`synthetic-example-value`. Rendrerens koblingssjekk godtar definisjonene.
Kontrollene passerer, og Secret samt volum fjernes ved opprydding.
