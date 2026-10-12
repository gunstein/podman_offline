# SELinux-kontroll etter run-6

Run-6 og originalbevisene er urørt. Fixturen er hentet fra den lesende
run-6-diagnosen: 23 forslag til relabeling og 143 meldinger om bevart tilpasset
label. Bare stier og contexts inngår, aldri filinnhold.

VM108: container-selinux 2.245.0, selinux-policy-targeted 38.1.75, Podman 5.8.2.
Kilder er kontrollert mot versjonstaggenes kildekode og lesende policyoppslag.

## Kilder og begrunnede regler

- **S1:** [container.if v2.245.0, linje 560](https://github.com/containers/container-selinux/blob/v2.245.0/container.if#L560)
  gir den navngitte overgangen `artifacts`: container_var_lib_t → container_ro_file_t.
  [container.te](https://github.com/containers/container-selinux/blob/v2.245.0/container.te#L493)
  bruker dette grensesnittet for named_filetrans_domain.
- **S2:** [container.fc v2.245.0](https://github.com/containers/container-selinux/blob/v2.245.0/container.fc#L114)
  gir container_var_lib_t som standard under /var/lib/containers, egne ro-regler
  for overlay/overlay-images/overlay-layers og container_file_t for voluminnhold.
  Derfor er `overlay-containers` container_var_lib_t med vår ekvivalens.
- **S3:** [Podman v5.8.2 setupStorage](https://github.com/containers/podman/blob/v5.8.2/libpod/container_internal.go#L556)
  oppretter userdata/artifacts med MkdirAll. S1 forklarer faktisk type, S2 forklarer
  restorecon-forslaget. `ARTIFACT_DIRECTORY_TRANSITION` godtar bare akkurat
  overlay-containers/<64 hex>/userdata/artifacts og ro → var_lib.
- **S4:** `/etc/selinux/targeted/contexts/customizable_types` på VM108 ble lest,
  uten endring, og inneholder container_file_t. Restorecon bevarer derfor disse
  tilpassede labels; «not reset as customized» er ikke et relabelingsforslag.
  [Podmans relabel-kode](https://github.com/containers/podman/blob/v5.8.2/libpod/container_internal_common.go#L3103)
  og [mount-label i overlay-driveren](https://github.com/containers/podman/blob/v5.8.2/vendor/go.podman.io/storage/drivers/overlay/overlay.go#L1874)
  forklarer private skrivbare labels. `CUSTOM_VOLUME_CONTENT` gjelder bare
  volumes/<navn>/_data med file → file. `CUSTOM_WRITABLE_LAYER` gjelder bare
  overlay/<64 hex>/diff med file → ro. `CUSTOM_WRITABLE_ROOTFS` gjelder bare
  overlay-containers/<64 hex>/rootfs/upper med file → var_lib.
  Alle krever at file-typen fortsatt er oppført som customizable på verten.
- **S5:** Lesende matchpathcon på VM108 gir var_lib_t for /var/lib/myproduct/.config.
  [Podmans CNI-initialisering](https://github.com/containers/podman/blob/v5.8.2/vendor/go.podman.io/common/libnetwork/cni/network.go#L100)
  oppretter cni.lock i brukerens config-katalog; [runtime-policyen](https://github.com/containers/container-selinux/blob/v2.245.0/container.te#L331)
  har overgang fra var_lib til container_var_lib ved runtime-oppretting.
  Run-6 opprettet ikke .config før første Podman-kall. Prosedyren skal nå
  preopprette .config/cni/net.d, cni.lock og .config/containers/systemd og kjøre restorecon
  før Podman. De ni linjene utenfor lageret er FAIL, aldri tillatte unntak.

## Kontroll A–E

A tester policy-prober for overlay-layers og voluminnhold, også uten eksisterende
filer. B sammenligner faktisk type mot selinux.matchpathcon for katalogene og
rekursivt voluminnhold. Overlay-lag skannes ikke rekursivt.

C krever tom restorecon dry-run utenfor storage. D logger alltid lagerets dry-run
og klassifiserer hver linje med reglene ovenfor. Uklassifiserte linjer gir FAIL.
Ingen generell regel for hele lageret finnes. E krever kjørende containere,
DB/OIDC, prod-e2e og ingen AVC/USER_AVC/FANOTIFY siden kjøringens start.
Alle kontroller er lesende: restorecon har alltid -n, aldri -F eller chcon.

## De 23 forslagene fra run-6

Stier nedenfor er relative til `/var/lib/myproduct/`. «Prosedyre» betyr at
linjen skal gi FAIL i kontrollen og forebygges av klargjøringsscriptet.

| Sti | Fra-type | Til-type | Regel / behandling | Kilde |
| --- | --- | --- | --- | --- |
| .local/share/containers/storage/overlay-containers/9253fdb7aab1cd99839b66e92622dcf83afec345488ce6d721ea8ebca6caf0d3/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/b3f642b372d5bb2e61a89ac0e0757fe21332e9a3d896717e466ee9d4ae496294/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/9451807b18733e8cf5fab13d07ac1cc7677b3096e86133aaf6b741796df63b36/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/12f7432b5dcf1594e3412e7787e19f47533ff3b0b611feb08ec011b834dfafbd/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/42244ed1911e5ab9460977937bb8931b71792ecfd1a88128ba9e2171c0507e5e/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/36f99871575c506c01189947a3a7031881ad398b2c2edb35d40dea17f62aa589/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/31a2fe5e2f45df2e2d146d377c44c6a288168ace762f7e966c1052d7638238dc/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/af34ee73fafcb3bfbdfd5988cf59a77b1c54a47a2cc707a1ff37012751bae57a/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/904c987406516f77b229a024c7f5744e9c0b1cd5e4f95a471e0dcfa7935daecf/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/8927689b7fbe9e64e55124eac280425175b346ef6a9b7552eae2eb34863b920e/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/e263592128fb6abff7de56dd35dedfbdbfc53bebe66d0f6ee7c661d8929fd72e/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/67196724fb5abe79f7da2f834bbd29c38847b70fbafba4931420960fc5c0bb22/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/69fecaa98e70688daaf7bea3720c3ebd5bf66849ae7749a850b52f58f18a35a4/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .local/share/containers/storage/overlay-containers/e6094e8d26ce9a5efcb80e475608d105a656a1298dc73f50134afcaf9a7948a2/userdata/artifacts | container_ro_file_t | container_var_lib_t | ARTIFACT_DIRECTORY_TRANSITION | S1–S3 |
| .config | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |
| .config/cni | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |
| .config/cni/net.d | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |
| .config/cni/net.d/cni.lock | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |
| .config/containers | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |
| .config/containers/systemd | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |
| .config/containers/systemd/myproduct.yaml | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |
| .config/containers/systemd/myproduct.kube | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |
| .config/containers/systemd/myproduct.network | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; preoppretting i prosedyren | S5 |

Fixture SHA256: aa7773749c48b5f286b270ab9d682005431491db95ddecca20de10759c0f2607

Lesende VM-kildebevis: `2026-10-12-run-6-policy-sources.log`, lagret utenfor repoet.
SHA256: 7eeb318a994df2dd8fc5ca317ba1b4f5ef202550d981fd582213179413d28ca6

Etter review av 2129852 krever `CUSTOM_WRITABLE_LAYER` dessuten at lag-ID-en
er oppgitt som `GraphDriver.Data.UpperDir` av inspect for en eksisterende
container. S4 begrunner labelen på et skrivbart container-lag, ikke på
et image-lag. UpperDir-oppslaget er lesende og logges i kontrollen.
