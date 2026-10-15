# secrets

Run `./examples/run.sh secrets` after [the image setup](../README.md).

Tests three `SECRET_FILES` ids: a directory with two text files, a binary file and
a separate Secret from the same text directory to test selection with `items`.
The binary file is generated at run time with all byte values 0–255, NUL, 0xff and CR/LF.
All mounts are read-only:

- `/inputs/text`: without `items`, both text files are mounted with their original names.
- `/inputs/binary`: explicit `items` with `key: binary.bin` and `path: binary.bin`,
  matching the pattern for a single PFX file.
- `/inputs/selected`: `items` selects only `message.txt` and places it as
  `renamed.txt`. The other key, `second.txt`, must not be mounted,
  and `message.txt` must not exist under its original name in this mount.

Expected: the SHA-256 of each file on the host equals the SHA-256 read with `podman exec`
from the container, also for the renamed file. Unselected keys must be missing.
No conversion of binary data is allowed. All checks
pass and the script returns 0. The Secrets and their named mount volumes
are removed at cleanup.

Tested with rootless Podman 5.7.0: the same file name in `key`/`path`, top-level
renaming and filtering out unselected keys work. The SHA-256 checks pass.
A separate trial with `path: nested/renamed.txt` failed at `kube play` with
exit 125 and the message `must not contain path separator`. Use a file name
without `/` in `items.path` on this version; the directory is chosen with `mountPath`.
