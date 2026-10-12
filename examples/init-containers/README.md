# init-containers

Kjør `./examples/run.sh init-containers` etter [image-oppsettet](../README.md).

To init-containere deler en manifestdefinert PVC med hovedcontaineren.
`first` skriver linjen `first`. `second` krever at denne finnes før den legger
til `second`. Hovedcontaineren sjekker begge linjene før den kopierer resultatet
til `/tmp/observed`. Host-scriptet leser og kontrollerer denne kopien.

Forventet: nøyaktig `first` og `second`, i den rekkefølgen. Hovedcontaineren
kan bare passere kontrollen etter begge init-containerne. Manglende/feil innhold
eller en container som ikke starter gir exit ulik 0. PVC-volumet ryddes bort.
