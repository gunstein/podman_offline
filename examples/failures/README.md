# failures

Run `./examples/run.sh failures`. Requires Python and PyYAML, but not Podman
or the local test image. Each sub-case has its own config and manifest.

| Case | Expected error message |
| --- | --- |
| `unused-id` | The VOLUME_FILES id “is not used by any manifest” |
| `unknown-claim` | PersistentVolumeClaim “does not exist” |
| `partial-placeholder` | “Unreplaced @@...@@” for an inline placeholder in a container env value (ConfigMap data and `SECRET_TEMPLATES` accept inline placeholders) |
| `large-secret` | The SECRET_FILES id “is too large” |

The large file is generated as 400,000 bytes in the temporary area. For each variant,
`./deploy prepare` must fail, the expected text must be in the output, and
neither `build/install.yaml` nor `build/files` may exist. The script itself
returns 0 only when all four expected errors are confirmed; a wrong cause or
an unexpectedly successful render gives a non-zero exit.
