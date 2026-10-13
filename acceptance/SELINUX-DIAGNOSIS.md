# SELinux check after run-6

Run-6 and the original evidence are untouched. The fixture comes from the read-only
run-6 diagnosis: 23 relabel proposals and 143 messages about preserved customized
labels. Only paths and contexts are included, never file content.

VM108: container-selinux 2.245.0, selinux-policy-targeted 38.1.75, Podman 5.8.2.
The sources were checked against the version tags' source code and read-only policy lookups.

## Sources and justified rules

- **S1:** [container.if v2.245.0, line 560](https://github.com/containers/container-selinux/blob/v2.245.0/container.if#L560)
  gives the named transition `artifacts`: container_var_lib_t → container_ro_file_t.
  [container.te](https://github.com/containers/container-selinux/blob/v2.245.0/container.te#L493)
  uses this interface for named_filetrans_domain.
- **S2:** [container.fc v2.245.0](https://github.com/containers/container-selinux/blob/v2.245.0/container.fc#L114)
  gives container_var_lib_t as the default under /var/lib/containers, separate ro rules
  for overlay/overlay-images/overlay-layers and container_file_t for volume content.
  That is why `overlay-containers` is container_var_lib_t with our equivalence.
- **S3:** [Podman v5.8.2 setupStorage](https://github.com/containers/podman/blob/v5.8.2/libpod/container_internal.go#L556)
  creates userdata/artifacts with MkdirAll. S1 explains the actual type, S2 explains
  the restorecon proposal. `ARTIFACT_DIRECTORY_TRANSITION` accepts only exactly
  overlay-containers/<64 hex>/userdata/artifacts and ro → var_lib.
- **S4:** `/etc/selinux/targeted/contexts/customizable_types` on VM108 was read,
  without changes, and contains container_file_t. Restorecon therefore keeps these
  customized labels; “not reset as customized” is not a relabel proposal.
  [Podman's relabel code](https://github.com/containers/podman/blob/v5.8.2/libpod/container_internal_common.go#L3103)
  and [the mount label in the overlay driver](https://github.com/containers/podman/blob/v5.8.2/vendor/go.podman.io/storage/drivers/overlay/overlay.go#L1874)
  explain the private writable labels. `CUSTOM_VOLUME_CONTENT` applies only to
  volumes/<name>/_data with file → file. `CUSTOM_WRITABLE_LAYER` applies only to
  overlay/<64 hex>/diff with file → ro. `CUSTOM_WRITABLE_ROOTFS` applies only to
  overlay-containers/<64 hex>/rootfs/upper with file → var_lib.
  All require that the file type is still listed as customizable on the host.
- **S5:** A read-only matchpathcon on VM108 gives var_lib_t for /var/lib/myproduct/.config.
  [Podman's CNI initialization](https://github.com/containers/podman/blob/v5.8.2/vendor/go.podman.io/common/libnetwork/cni/network.go#L100)
  creates cni.lock in the user's config directory; [the runtime policy](https://github.com/containers/container-selinux/blob/v2.245.0/container.te#L331)
  has a transition from var_lib to container_var_lib when the runtime creates files.
  Run-6 did not create .config before the first Podman call. The procedure now
  creates .config/cni/net.d, cni.lock and .config/containers/systemd first and runs restorecon
  before Podman. The nine lines outside storage are FAIL, never allowed exceptions.

## Checks A–E

A tests policy probes for overlay-layers and volume content, also without existing
files. B compares the actual type with selinux.matchpathcon for the directories and
the volume content recursively. Overlay layers are not scanned recursively.

C requires an empty restorecon dry run outside storage. D always logs the storage dry run
and classifies each line with the rules above. Unclassified lines give FAIL.
There is no general rule for the whole storage. E requires running containers,
DB/OIDC, prod e2e and no AVC/USER_AVC/FANOTIFY since the start of the run.
All checks are read-only: restorecon always has -n, never -F or chcon.

## The 23 proposals from run-6

The paths below are relative to `/var/lib/myproduct/`. “Created first by the procedure” means that
the line must give FAIL in the check and is prevented by the preparation script.

| Path | From type | To type | Rule / handling | Source |
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
| .config | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |
| .config/cni | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |
| .config/cni/net.d | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |
| .config/cni/net.d/cni.lock | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |
| .config/containers | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |
| .config/containers/systemd | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |
| .config/containers/systemd/myproduct.yaml | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |
| .config/containers/systemd/myproduct.kube | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |
| .config/containers/systemd/myproduct.network | container_var_lib_t | var_lib_t | OUTSIDE_STORAGE_FAIL; created first by the procedure | S5 |

Fixture SHA256: aa7773749c48b5f286b270ab9d682005431491db95ddecca20de10759c0f2607

Read-only VM source evidence: `2026-10-12-run-6-policy-sources.log`, stored outside the repo.
SHA256: 7eeb318a994df2dd8fc5ca317ba1b4f5ef202550d981fd582213179413d28ca6

After the review of 2129852, `CUSTOM_WRITABLE_LAYER` also requires that the layer ID
is reported as `GraphDriver.Data.UpperDir` by inspect for an existing
container. S4 justifies the label on a writable container layer, not on
an image layer. The UpperDir lookup is read-only and logged in the check.
