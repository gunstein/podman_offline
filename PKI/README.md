# Lokal test-PKI

Kjør `./PKI/generate.sh` eller `./scripts/generate-certificates.sh` fra repo-roten.
`PKI/generate.sh` er en wrapper rundt `scripts/generate-certificates.sh`.
Scriptet i `scripts/` følger med offline-bundlen og oppretter PKI-katalogen ved behov. Standard TLS-navn er `myproduct-proxy`; valgfritt første
argument angir et annet DNS-navn.

I prod brukes `bash scripts/generate-certificates.sh --root /var/lib/myproduct
myproduct-proxy` (på én linje, som tjenestebrukeren). Da ligger nøkler,
passord og CA utenfor release-katalogen. Standard uten `--root` er fortsatt
prosjektroten. Generer bare ved første installasjon, aldri ved oppgradering;
databaser og demobrukere beholder sine opprinnelige passord. CA på målverten
er kun for demo; i ekte prod utstedes sertifikater eksternt.

CA-nøkkel og CA-sertifikat genereres i `PKI/private/`. Tre separate nøkkelpar
signeres av CA-en:

| Filer | Bruk | Leveranse til pod |
| --- | --- | --- |
| `generated-certificates/identity/identity.{key,crt}` | Duende signerer OIDC-token | Secret |
| `generated-certificates/todo/todo-client.{key,crt}` | Todo autentiserer klienten med private_key_jwt | PVC via VOLUME_FILES |
| `generated-certificates/web/web.{key,crt}` | nginx HTTPS | Secret |

Duende får i tillegg en kopi av Todo-klientens offentlige sertifikat i
`generated-certificates/client/`. Todo-volumet får CA-sertifikatet for HTTPS-
verifisering og en separat tilfeldig cookie-signeringhemmelighet. Det opprettes
også tilfeldige databasepassord og passord for demo-brukerne alice/bob.

Alle utdata opprettes med `umask 077` og er ignorert av Git. CA-sertifikatet kan
importeres i nettleseren; CA-privatnøkkelen skal bli hos den som utsteder
sertifikatene. Scriptet avviser en ny kjøring når nøkkelmateriale allerede finnes,
slik at en gjentatt kommando ikke bytter nøkler eller passord under en kjørende app.

Todo-privatnøkkelen ligger i PVC som ønsket. Den er sensitiv selv om den er en
volumfil: deploy normaliserer filmodusen i importarkivet til 0644. Bare backenden
monterer volumet, read-only. Beskytt vertens Podman-lager og sikkerhetskopier.
Bytt nøkkel og oppdater både Todo-PVC og Duendes offentlige klientsertifikat
samtidig ved senere rotasjon. Dette scriptet implementerer ikke automatisk rotasjon.
