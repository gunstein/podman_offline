# Manuell prod-test på en VM

Bruk en disponibel VM med samme Podman-versjon, OS/systemd og sikkerhetsoppsett
som målnettet. Prod bruker rootless Podman som `myproduct`, med hjem
`/var/lib/myproduct`. Denne sjekklisten er manuell; automatisert kjøring og bevis
finnes i [akseptansetesten](../acceptance/README.md).

1. Følg klargjøringen i [prod-flyten i README](../README.md#offline-bundle-og-rootless-quadlet):
   ytre checksum, midlertidig utpakking, prepare-host, utpakking som myproduct,
   indre checksums, trust av kun deploy.py og demo-sertifikater/config. Vent med
   install til steg 2 nedenfor. Ingen
   private nøkler eller passord skal i Git eller logger. VM-en skal være uten
   internett før bundlen overføres. Registrer OS, Podman og systemd-versjon.
2. Som operatør med sudo, definer kommandohjelperen og installer fra releasen.
   HOME og arbeidskatalog må begge tilhøre tjenestebrukeren; `sudo -H` alene
   bytter ikke arbeidskatalog. Shell-script kjøres med bash.

   ```sh
   as_product() {
       sudo -H -u myproduct bash -c '
           cd "$HOME" || exit
           export XDG_RUNTIME_DIR="/run/user/$(id -u)"
           exec "$@"
       ' bash "$@"
   }
   release=/var/lib/myproduct/releases/myproduct-0.1.0
   sudo -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$release"
   sudo systemctl --user -M myproduct@ status myproduct.service --no-pager
   sudo systemctl --user -M myproduct@ status myproduct-network.service --no-pager
   as_product podman network inspect myproduct
   as_product podman ps --all --pod
   as_product podman secret ls
   as_product podman volume ls
   ```

   Forvent aktiv tjeneste og sju kjørende appcontainere. Test Todo, innlogging og
   hjelpesidene over HTTPS fra en annen maskin med korrekt CA/navn. Bruk smoke og
   markørtesten i acceptance for å kontrollere data for både Alice og Bob.
3. Kontroller filrettigheter, SELinux og linger:

   ```sh
   sudo stat -c '%U:%G %a %n' /var/lib/myproduct
   sudo stat -c '%U:%G %a %n' /var/lib/myproduct/.config/containers/systemd/myproduct.{yaml,kube,network}
   sudo stat -c '%U:%G %a %n' /var/lib/myproduct/files
   sudo find /var/lib/myproduct/files -maxdepth 1 -type f -exec stat -c '%U:%G %a %n' {} \;
   sudo ls -Zd /var/lib/myproduct /var/lib/myproduct/.local/share/containers/storage
   sudo loginctl show-user myproduct -p Linger -p State -p RuntimePath
   getenforce
   systemctl is-active fapolicyd
   ```

   Forvent myproduct:myproduct, hjem/filkatalog 0700, YAML/arkiver 0600 og
   kube/network 0644. SELinux skal være Enforcing og fapolicyd aktiv.
   Overlay, overlay-layers og overlay-images skal ha container_ro_file_t;
   overlay-containers skal ha container_var_lib_t og voluminnhold container_file_t.
   Kontroller faktiske typer mot selinux.matchpathcon, som steg 07 gjør.
   Kjør `sudo restorecon -n -v -R -e /var/lib/myproduct/.local/share/containers/storage /var/lib/myproduct`;
   output utenfor lageret skal være tom. Logg separat dry-run av storage og
   klassifiser hver linje etter [reglene](../acceptance/SELINUX-DIAGNOSIS.md).
   Ukjente linjer og AVC/USER_AVC/FANOTIFY siden teststart gir FAIL.
   Kjør aldri restorecon -R eller -F på et fylt lager.
   Registrer faktiske labels; ikke slå av sikkerhetsmekanismer ved avvisninger.
4. Kontroller generator, nettavhengigheter og DNS:

   ```sh
   as_product /usr/lib/systemd/user-generators/podman-user-generator --dryrun
   sudo systemctl --user -M myproduct@ cat myproduct.service
   sudo systemctl --user -M myproduct@ cat myproduct-network.service
   as_product podman exec myproduct-todo-backend python -c 'import socket; socket.create_connection(("myproduct-todo-postgres",5432),5).close()'
   as_product podman exec myproduct-proxy-nginx wget -qO- http://myproduct-identity:8080/identity/.well-known/openid-configuration
   ```

   Forvent nettavhengighet mot myproduct-network.service og
   podman-user-wait-network-online.service, samt WantedBy=default.target.
5. Opprett Todo-markører for begge brukerne. Etter hver overgang skal tjenesten
   være aktiv, alle appcontainere kjøre og markørene fortsatt finnes:

   ```sh
   sudo systemctl --user -M myproduct@ stop myproduct.service
   as_product podman ps --all --pod
   as_product podman secret ls
   as_product podman volume ls
   sudo systemctl --user -M myproduct@ start myproduct.service
   # Kontroller status, HTTPS og markører før neste overgang.
   sudo systemctl --user -M myproduct@ restart myproduct.service
   # Registrer PID, starttid og restart-teller før krasjet.
   as_product podman inspect --format '{{.State.Pid}} {{json .State.StartedAt}} {{.RestartCount}}' myproduct-todo-backend
   pid=$(as_product podman inspect --format '{{.State.Pid}}' myproduct-todo-backend)
   [[ $pid =~ ^[0-9]+$ && $pid -gt 1 ]] || exit 1
   sudo -n kill -KILL "$pid"
   ```

   Secret-volumene blir liggende på disk etter stopp. Følg README for sletting.
   Etter det uventede prosesskrasjet kreves automatisk retur innen 60 sekunder:
   Running=true, restart-teller økt med én, ny PID og starttid, StoppedByUser=false.
   Kontroller deretter alle containere, `/api/health` via HTTPS-proxyen med CA
   og markørene. Rammeverkets `09-crash` parser inspect-JSON og verifiserer alle
   disse feltene automatisk. `podman kill` markerer eksplisitt brukerstopp og
   brukes derfor ikke til denne krasjtesten. Ikke start eller reparer en
   container som ikke kommer tilbake; registrer avviket og stopp testen.
6. Hvis foregående steg passerer, registrer boot-ID og utfør ekte reboot:

   ```sh
   cat /proc/sys/kernel/random/boot_id
   sudo reboot
   ```

   Etter ny SSH-innlogging som operatør, uten innlogging som myproduct og uten
   install/start først: kontroller ny boot-ID, brukerens tjeneste, containere,
   markører, full e2e og at internett fortsatt er blokkert. Definer as_product
   på nytt i den nye skallsesjonen. Linger skal gi oppstart uten brukerinnlogging.
7. Følg README sin oppgraderingsflyt med ny VERSION. Bruk de samme passordene
   til full e2e og kontroller markørene fra steg 5. Sammenlign CA-fingeravtrykk
   og SHA256 for generated-certificates før/etter; ingen fil skal endres.
   Kontroller at gammel deploy.py er fjernet fra trust-databasen.
   Ikke generer sertifikater eller erstatt config ved oppgradering.
8. Registrer alle avvik og hent lesende journal/audit. Ikke logg nøkkel- eller
   passordinnhold og ikke slett data for å få testen til å passere.

   ```sh
   sudo journalctl _SYSTEMD_USER_UNIT=myproduct.service _UID="$(id -u myproduct)" --no-pager
   # Sett start til epoch registrert før kjøringen.
   start_date=$(LC_ALL=C date -d "@$start" +%x)
   start_time=$(date -d "@$start" +%H:%M:%S)
   sudo env LC_ALL=C ausearch --input-logs -m FANOTIFY,AVC,USER_AVC -ts "$start_date" "$start_time" -i </dev/null
   ```

   Dato og tid er separate argumenter. `%x` under C-lokalen gir formatet som
   VM-ens ausearch krever. Ta med avvisninger også når funksjonstestene passerer.

Helsesjekker: se alle containere med `as_product podman ps`, og les hver status
med `as_product podman inspect --format '{{.State.Health.Status}}' <container>`.
Alle appcontainere skal være running og healthy. InitialDelay 90 sekunder dekker
oppstarten; starting er forventet i inntil 90 sekunder etter hver start, før neste
sjekk lykkes. Kjør ved behov `as_product podman healthcheck run <container>`.

Akseptansens `09-hang` fryser backendens vertsprosesser med SIGSTOP, etter at
PID-ene er lest med `podman top myproduct-todo-backend hpid`. Den krever unhealthy,
nøyaktig én automatisk restart, ny PID/starttid og healthy innen 240 sekunder,
uten StoppedByUser. Etterpå kontrolleres alle manifestdefinerte containere,
HTTPS og markører. Ikke bruk podman pause/stop/kill eller manuell SIGCONT;
ved feil stoppes testen og bare lesende diagnose utføres.
