# manifest-defined

Run `./examples/run.sh manifest-defined` after [the image setup](../README.md).

Both the app data PVC and a Secret are defined directly in the manifest, without
`SECRET_FILES` or `VOLUME_FILES`. The Secret uses `stringData` with a clearly
synthetic value. The container reads the value through `env.valueFrom.secretKeyRef`
and writes it to the PVC volume.

Expected: both the environment variable `TOKEN` and the file `/data/token-seen` contain
`synthetic-example-value`. The renderer's link check accepts the definitions.
The checks pass, and the Secret and the volume are removed at cleanup.
