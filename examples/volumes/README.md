# volumes

Run `./examples/run.sh volumes` after [the image setup](../README.md).

Tests a `VOLUME_FILES` id with a separate file and a directory tree. The directory's
content must be directly in `/data`, without an extra `tree/` directory.
SHA-256 is checked for every uploaded file. From the container, the
file must be owned by `0:0` with 0644, the directory by `0:0` with 0755, and the executable
script by `0:0` with 0755. In rootless mode this shows owners in the container's
user namespace, not the host's numeric user IDs.

Then the app writes `/data/app-created.txt` and overwrites `/data/single.txt`.
The script runs `kube down` without removing the volume, changes the uploaded
source file, runs `prepare` again and plays the YAML again.

Expected: the app's own file is kept, while `single.txt` equals the newly
uploaded file. If the Podman version does not import over an existing
volume, the last SHA-256 check fails and the script returns non-zero.
The volume is deleted after the test, also on verification failures.

The source list uses `{path: files/single.txt}` and directory mappings. The same
format permits optional `generate: [filename]` on a local directory source;
this example uses provided files without generation.
