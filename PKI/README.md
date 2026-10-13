# Local test PKI

Run `./PKI/generate.sh` or `./scripts/generate-certificates.sh` from the repo root.
`PKI/generate.sh` is a wrapper around `scripts/generate-certificates.sh`.
The script in `scripts/` ships with the offline bundle and creates the PKI directory when needed. The default TLS name is `myproduct-proxy`; an optional first
argument sets another DNS name.

In prod, use `bash scripts/generate-certificates.sh --root /var/lib/myproduct
myproduct-proxy` (on one line, as the service user). Keys,
passwords and the CA then live outside the release directory. Without `--root` the default is still
the project root. Generate only at the first installation, never when upgrading;
databases and demo users keep their original passwords. A CA on the target host
is for the demo only; in real prod, certificates are issued externally.

The CA key and CA certificate are generated in `PKI/private/`. Three separate key pairs
are signed by the CA:

| Files | Use | Delivered to the pod as |
| --- | --- | --- |
| `generated-certificates/identity/identity.{key,crt}` | Duende signs OIDC tokens | Secret |
| `generated-certificates/todo/todo-client.{key,crt}` | Todo authenticates the client with private_key_jwt | PVC via VOLUME_FILES |
| `generated-certificates/web/web.{key,crt}` | nginx HTTPS | Secret |

Duende also gets a copy of the Todo client's public certificate in
`generated-certificates/client/`. The Todo volume gets the CA certificate for HTTPS
verification and a separate random cookie signing secret. Random
database passwords and passwords for the demo users alice/bob are created as well.

All output is created with `umask 077` and is ignored by Git. The CA certificate can be
imported into the browser; the CA private key must stay with whoever issues
the certificates. The script rejects a new run when key material already exists,
so that a repeated command does not replace keys or passwords under a running app.

The Todo private key lives in a PVC as intended. It is sensitive even though it is a
volume file: deploy normalizes the file mode in the import archive to 0644. Only the backend
mounts the volume, read-only. Protect the host's Podman storage and backups.
Replace the key and update both the Todo PVC and Duende's public client certificate
together in a later rotation. This script does not implement automatic rotation.
