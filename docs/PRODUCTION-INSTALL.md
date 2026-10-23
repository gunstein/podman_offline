# Kort produksjonsinstallasjon: eksisterende bruker og separat lagring

**Status: planlagt i [backlog item 64](../BACKLOG.md#64-support-new-rootless-installations-outside-the-login-home).**
Dette beskriver avtalt installasjonsflyt, ikke funksjonalitet som finnes ferdig
i dagens bundle. Implementeringsagenten skal erstatte denne statusen med
verifiserte kommandoer før veiledningen brukes til installasjon. Dagens
`prepare-host.sh` krever fremdeles hjem under `/var/lib/<bruker>` og `nologin`;
ikke flytt brukerhjemmet eller endre shell for å omgå dette.

## Forutsetninger og plassering

Målet er en ny, offline installasjon på Oracle Linux 9 med SELinux Enforcing og
fapolicyd aktiv. Bruk en eksisterende, ikke-privilegert konto med vanlig
innlogging. Brukernavn, UID og hjemmekatalog kan variere; kontoen må ikke allerede
kjøre et annet produkt. Produktet `sms` er et eksempel, ikke et hardkodet navn.

| Plassering i eksemplet | Formål og eierskap |
| --- | --- |
| `~/.sms/sms.env` | Installasjonsinnstillinger; eies av driftsbrukeren, katalog `0700`, fil `0600` |
| `/var/lib/sms` | Root-eid anker; driftsbrukeren kan ikke erstatte underkatalogene |
| `/var/lib/sms/releases/` | Verifiserte releaser; root-eide og lesbare for driftsbrukeren |
| `/var/lib/sms/state/` | Komponentconfig, credentials og installasjonsstatus; privat for driftsbrukeren |
| `/var/lib/sms/storage/` | Podman-images og volumer; klargjort for driftsbrukeren, med Podmans UID-mappinger internt |
| `/var/lib/sms/config/` | Podman-/Quadlet-konfigurasjon; skrivbar for driftsbrukeren |

Produktets øvrige vedvarende filer, mellomlagring og importarkiver skal også
plasseres under installasjonsroten. Systemets `/run/user/<uid>`, systemjournal og
administratorens konfigurasjon i `/etc` beholder sine normale plasseringer.
SELinux- og fapolicyd-oppsett må dekke de valgte stiene.

## Installasjonsrekkefølge

1. **Operatør: overfør bundles.** Ta med platform, STS og eventuelle deklarerte
   avhengigheter, med `.sha256` og `.asc` dersom de er signert. Offentlig
   signeringsnøkkel leveres gjennom en betrodd kanal. Målmaskinen må allerede ha
   nødvendige OS-pakker; installasjonen skal ikke hente images eller pakker fra
   nett. Legg arkivene i klargjort innleveringsområde under installasjonsroten
   eller på overføringsmediet, ikke i den plassbegrensede hjemmekatalogen.
2. **Administrator: klargjør verten.** Velg faktisk driftsbruker, produkt og
   installasjonsrot eksplisitt. Klargjør avgrensede katalogrettigheter, rootless
   UID/GID-mappinger, linger, SELinux, fapolicyd og HTTPS-porten. Behold brukerens
   eksisterende hjem og shell. Unngå rekursiv `chown` av hele installasjonsroten.
3. **Administrator: verifiser og publiser releasene.** Bruk det delte,
   beskyttede release-verktøyet fra item 54. Verifiser signatur etter gjeldende
   policy og checksums før bruk av kode fra arkivet. Usignerte testbundles
   krever en eksplisitt tillatt testflyt. Publiser root-eide releaser og vent på
   riktig fapolicyd-trust. Dette privilegerte steget gjelder også nye releaser
   ved oppgradering.
4. **Driftsbruker: opprett installasjonsinnstillingene.** Skriv `~/.sms/sms.env`
   med de dokumenterte bootstrap-feltene for produktets installasjonsrot.
   Installerte kommandoer og systemd må bruke samme stier uten manuell eksport
   i terminalen. Filen kjøres ikke som shellkode av root og overskriver ikke
   eksisterende komponentconfig automatisk.
5. **Driftsbruker: installer platform, deretter STS.** For hver komponent:
   kjør `init-config` fra dens publiserte release, rediger vedvarende config,
   klargjør nødvendige credentials, kjør `validate`, og deretter `install`.
   Bruk port `8443` konsekvent, korrekt DNS-navn i `PUBLIC_ORIGIN` og serverens
   adresse i `IP_ADDRESS` dersom andre maskiner skal nå proxyen. Platform trenger
   websertifikat; STS trenger sine erklærte credentials og eventuelt signing-PFX.
   Dev-passord, sertifikater og `config.dev.yaml` følger ikke med. Bekreft
   produksjonens migrerings-/seed-valg før første oppstart.
6. **Driftsbruker og administrator: verifiser.** Kontroller unit-/containerhelse,
   `/livez`, `/sts/` og innlogging med riktig eksternt vertsnavn. Test restart,
   utlogging og en avtalt reboot; tjenestene skal starte uten interaktiv login
   eller terminalmiljø. Kontroller faktisk Podman-lagring, at produktet ikke
   legger data i hjemmekatalogen, og at SELinux/fapolicyd fortsatt håndheves.

Start, stopp, status og vanlig drift skal kjøres rootless uten sudo. Vertsoppsett
og publisering/trust av nye releaser er administratoroppgaver. Ikke bruk
`sudo podman` eller sett et falskt `HOME` for å få dette til å fungere.

## Før veiledningen kan regnes som ferdig

Item 64 skal levere konkrete, kopierbare kommandoer for stegene over, med faktisk
CLI-navn og implementerte felter i `sms.env`. Bruk ett sammenhengende eksempel
med produkt `sms`, et annet brukernavn og individuelle bundle-versjoner. Vis
hvilken bruker som kjører hvert steg, hvor config/credentials skal ligge, og hva
som bekrefter suksess. Kommandoene skal testes fra en fersk OL9-installasjon;
simulerte harness-tester er ikke bevis på at denne operatørflyten fungerer.
