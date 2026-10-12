# Manuell prod-test på en VM

Denne sjekklisten skal utføres manuelt. Den er ikke kjørt av eksempelrunneren.
Bruk en disponibel VM med samme Podman-versjon, OS/systemd og sikkerhetsoppsett
som målnettet. Alle Podman-kommandoer nedenfor kjøres rootful med `sudo`.
Eksempelrunnerens rootless-resultater erstatter ikke denne prøven.

1. Skaff en komplett produkt-bundle (inkludert images, prod-manifester og
   Quadlet). Verifiser ytre `.sha256`, pakk ut og kjør `sha256sum -c checksums.sha256`
   fra bundle-roten. Registrer `podman --version`, `systemctl --version` og OS.
2. Kopier `config.example.yaml` til `config.yaml`, tilpass vert/IP/port og
   generer lokale testsertifikater med produktets medfølgende script. Bruk
   bare syntetiske testdata. Ikke legg private nøkler eller sertifikater i git.
3. Koble VM-en fra internett og kjør fra bundle-roten:

   ```sh
   sudo ./deploy install
   sudo systemctl status myproduct.service --no-pager
   sudo systemctl is-active myproduct.service
   sudo podman ps --all --pod
   sudo podman secret ls
   sudo podman volume ls
   ```

   Forvent aktiv tjeneste og kjørende appcontainere. Verifiser appens faktiske
   HTTPS-endepunkt med riktig test-CA, port og vertsnavn, samt at filene er
   tilgjengelige inne i containerne.
4. Kontroller installerte filer og eiere:

   ```sh
   sudo stat -c '%U:%G %a %n' /etc/containers/systemd/myproduct.yaml
   sudo stat -c '%U:%G %a %n' /etc/containers/systemd/myproduct.kube
   sudo stat -c '%U:%G %a %n' /var/lib/myproduct/files
   sudo find /var/lib/myproduct/files -maxdepth 1 -type f -exec stat -c '%U:%G %a %n' {} \;
   ```

   Forvent root:root, YAML/arkiver 0600, kube 0644 og filkatalog 0700.
   Filkatalog/arkiver finnes bare når config faktisk bruker `VOLUME_FILES`.
5. Kontroller generatoren og den genererte tjenesten:

   ```sh
   sudo /usr/lib/systemd/system-generators/podman-system-generator --dryrun
   sudo systemctl cat myproduct.service
   sudo journalctl -u myproduct.service --no-pager
   ```

   Forvent ingen generatorfeil og at tjenesten peker på den installerte YAML-en.
   Verifiser at den medfølgende Quadletens `[Install]`-oppsett gir oppstart ved boot.
6. Opprett en markørfil i appdatavolumet via `sudo podman exec` med det faktiske
   containernavnet og appdatastien. Endre også en importert fil i containeren.
   Test deretter hver overgang, og sjekk status, apprespons, secrets og volumer:

   ```sh
   sudo systemctl stop myproduct.service
   sudo podman ps --all --pod
   sudo podman secret ls
   sudo podman volume ls
   sudo systemctl start myproduct.service
   sudo systemctl status myproduct.service --no-pager
   sudo systemctl restart myproduct.service
   sudo systemctl status myproduct.service --no-pager
   ```

   Forvent at appdata/markøren beholdes, at importerte filer gjenopprettes fra
   arkivene ved oppstart, og at Secrets har forventet livssyklus ved stop/start.
7. Utfør en **ekte reboot** manuelt:

   ```sh
   sudo reboot
   ```

   Etter ny innlogging, uten å kjøre install/start først:

   ```sh
   sudo systemctl status myproduct.service --no-pager
   sudo journalctl -b -u myproduct.service --no-pager
   sudo podman ps --all --pod
   sudo podman secret ls
   sudo podman volume ls
   ```

   Kontroller apprespons, markørfil og importerte filer igjen. Arkivene må
   være tilgjengelige i `/var/lib/myproduct/files` uavhengig av bundle-katalogen.
8. Registrer versjoner, alle avvik og forventet/faktisk oppførsel. Ved feil:
   bruk journalen og generatorens `--dryrun`. Ikke slett appdatavolumer for å
   få testen til å passere; det ville skjule problemer med persistens.
