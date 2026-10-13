# Demo PKI

`scripts/generate-certificates.sh [--root DIR] core|app1|app2|help [DNS hostname]`
creates missing component material once. `PKI/generate.sh` forwards arguments to
that script. Dev uses build/dev; prod passes --root /var/lib/myproduct explicitly.
The shared CA lives in PKI/private. Core has identity signing and web TLS pairs,
its database password and shared demo-user passwords. Each app has a separate
client pair and database password. Session/API keys use GENERATED_SECRETS.

Identity receives only each client's public certificate; its private key and CA
certificate reach the own Todo through its signing PVC. All directories/files
are created privately. Repeating generation preserves existing nonempty files;
partial certificate/CA pairs and empty password files fail. Adding app2 retains
core/app1 material, except the CA serial advances when a new certificate is issued.

No keys, passwords or certificates are committed. A CA private key on the target
is for the demo only: real production issues certificates elsewhere and delivers
them to the persistent component paths. Do not replace database passwords or the
CA during an upgrade. Keep private state outside releases and back it up.
