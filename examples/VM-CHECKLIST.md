# Manual prod test on a VM

Use a disposable VM with the same Podman version, OS/systemd and security setup
as the target network. Prod uses rootless Podman as `myproduct`, with home
`/var/lib/myproduct`. This checklist is manual; automated runs and evidence
are in the [acceptance test](../acceptance/README.md).

1. Follow the preparation in the [prod flow in the README](../README.md#offline-bundle-and-rootless-quadlet):
   outer checksum, temporary unpacking, prepare-host, unpacking as myproduct,
   inner checksums, trust of deploy.py only and demo certificates/config. Wait with
   install until step 2 below. No
   private keys or passwords may go into Git or logs. The VM must be without
   internet before the bundle is transferred. Record the OS, Podman and systemd versions.
2. As an operator with sudo, define the command helper and install from the release.
   HOME and the working directory must both belong to the service user; `sudo -H` alone
   does not change the working directory. Shell scripts run with bash.

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

   Expect an active service and seven running app containers. Test Todo, sign-in and
   the help pages over HTTPS from another machine with the correct CA/name. Use the smoke and
   marker tests in acceptance to check data for both Alice and Bob.
3. Check file permissions, SELinux and linger:

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

   Expect myproduct:myproduct, home/files directory 0700, YAML/archives 0600 and
   kube/network 0644. SELinux must be Enforcing and fapolicyd active.
   Overlay, overlay-layers and overlay-images must have container_ro_file_t;
   overlay-containers must have container_var_lib_t and volume content container_file_t.
   Check the actual types against selinux.matchpathcon, as step 07 does.
   Run `sudo restorecon -n -v -R -e /var/lib/myproduct/.local/share/containers/storage /var/lib/myproduct`;
   the output outside storage must be empty. Log a separate dry run of storage and
   classify every line according to [the rules](../acceptance/SELINUX-DIAGNOSIS.md).
   Unknown lines and AVC/USER_AVC/FANOTIFY since the test start give FAIL.
   Never run restorecon -R or -F on populated storage.
   Record the actual labels; do not turn off security mechanisms on denials.
4. Check the generator, network dependencies and DNS:

   ```sh
   as_product /usr/lib/systemd/user-generators/podman-user-generator --dryrun
   sudo systemctl --user -M myproduct@ cat myproduct.service
   sudo systemctl --user -M myproduct@ cat myproduct-network.service
   as_product podman exec myproduct-todo-backend python -c 'import socket; socket.create_connection(("myproduct-todo-postgres",5432),5).close()'
   as_product podman exec myproduct-proxy-nginx wget -qO- http://myproduct-identity:8080/identity/.well-known/openid-configuration
   ```

   Expect a network dependency on myproduct-network.service and
   podman-user-wait-network-online.service, plus WantedBy=default.target.
5. Create Todo markers for both users. After every transition the service must
   be active, all app containers running and the markers still present:

   ```sh
   sudo systemctl --user -M myproduct@ stop myproduct.service
   as_product podman ps --all --pod
   as_product podman secret ls
   as_product podman volume ls
   sudo systemctl --user -M myproduct@ start myproduct.service
   # Check status, HTTPS and markers before the next transition.
   sudo systemctl --user -M myproduct@ restart myproduct.service
   # Record PID, start time and restart count before the crash.
   as_product podman inspect --format '{{.State.Pid}} {{json .State.StartedAt}} {{.RestartCount}}' myproduct-todo-backend
   pid=$(as_product podman inspect --format '{{.State.Pid}}' myproduct-todo-backend)
   [[ $pid =~ ^[0-9]+$ && $pid -gt 1 ]] || exit 1
   sudo -n kill -KILL "$pid"
   ```

   The Secret volumes stay on disk after a stop. Follow the README to delete them.
   After the unexpected process crash, an automatic return within 60 seconds is required:
   Running=true, restart count increased by one, a new PID and start time, StoppedByUser=false.
   Then check all containers, `/api/health` through the HTTPS proxy with the CA
   and the markers. The harness's `09-crash` parses inspect JSON and verifies all
   these fields automatically. `podman kill` marks an explicit user stop and
   is therefore not used for this crash test. Do not start or repair a
   container that does not come back; record the deviation and stop the test.
6. If the previous step passes, record the boot ID and do a real reboot:

   ```sh
   cat /proc/sys/kernel/random/boot_id
   sudo reboot
   ```

   After a new SSH login as the operator, without logging in as myproduct and without
   running install/start first: check the new boot ID, the user's service, containers,
   markers, full e2e and that internet is still blocked. Define as_product
   again in the new shell session. Linger must start the service without a user login.
7. Follow the README's upgrade flow with a new VERSION. Use the same passwords
   for full e2e and check the markers from step 5. Compare the CA fingerprint
   and SHA256 for generated-certificates before/after; no file may change.
   Check that the old deploy.py has been removed from the trust database.
   Do not generate certificates or replace the config when upgrading.
8. Record all deviations and collect the journal/audit read-only. Do not log key or
   password content and do not delete data to make the test pass.

   ```sh
   sudo journalctl _SYSTEMD_USER_UNIT=myproduct.service _UID="$(id -u myproduct)" --no-pager
   # Set start to the epoch recorded before the run.
   start_date=$(LC_ALL=C date -d "@$start" +%x)
   start_time=$(date -d "@$start" +%H:%M:%S)
   sudo env LC_ALL=C ausearch --input-logs -m FANOTIFY,AVC,USER_AVC -ts "$start_date" "$start_time" -i </dev/null
   ```

   Date and time are separate arguments. `%x` under the C locale gives the format that
   the VM's ausearch requires. Include denials even when the functional tests pass.

Health checks: list all containers with `as_product podman ps`, and read each status
with `as_product podman inspect --format '{{.State.Health.Status}}' <container>`.
All app containers must be running and healthy. The 90-second initialDelay covers
startup; starting is expected for up to 90 seconds after each start, until the next
check succeeds. When needed, run `as_product podman healthcheck run <container>`.

The acceptance step `09-hang` freezes the backend's host processes with SIGSTOP, after
reading the PIDs with `podman top myproduct-todo-backend hpid`. It requires unhealthy,
exactly one automatic restart, a new PID/start time and healthy within 240 seconds,
without StoppedByUser. Afterwards all manifest-defined containers,
HTTPS and markers are checked. Do not use podman pause/stop/kill or a manual SIGCONT;
on failure the test stops and only read-only diagnosis is done.
