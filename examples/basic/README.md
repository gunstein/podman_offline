# basic

Kjør `./examples/run.sh basic` fra repo-roten etter image-oppsettet i
[oversikten](../README.md). Standardporten er 18080; bruk `EXAMPLE_PORT=18081`
hvis den er opptatt.

Tester ConfigMap via `envFrom`, tekst og heltall gjennom placeholders,
ConfigMap-verdier som strenger, samt `hostPort` og `hostIP: 127.0.0.1`.
BusyBox httpd lytter på containerport 8080. Config-nøkkelen heter fortsatt
`HTTPS_PORT` fordi deploy krever den, men denne testserveren bruker vanlig HTTP.

Forventet: `curl` får `hello from config|42|18080`, miljøvariablene stemmer,
og `podman port` viser nøyaktig `127.0.0.1:18080`. Ved overstyring av port
endres forventet svar tilsvarende. Scriptet avslutter med PASS og exit 0.
