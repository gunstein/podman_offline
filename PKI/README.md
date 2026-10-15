# Demo PKI

`scripts/generate-certificates.sh [--root DIR] platform|app1|app2|help [DNS hostname]`
creates missing component material once. `PKI/generate.sh` forwards arguments to
that script. Dev uses build/dev; prod passes --root /var/lib/myproduct explicitly.
The shared CA lives in PKI/private. Platform has identity signing and web TLS pairs,
shared demo-user passwords. Each app has a separate client pair. Database
passwords and session/API keys belong to deploy’s GENERATED_SECRETS mechanism,
not this certificate script. See the PostgreSQL section in the root README for
state preflight, persistent paths, backup/recovery and manual config additions.

Identity receives only each client's public certificate; its private key and CA
certificate reach the own Todo through its signing PVC. All directories/files
are created privately. Repeating generation preserves existing nonempty files;
partial certificate/CA pairs and empty demo-user password files fail. Database
password validation happens in deploy’s lifecycle preflight. Adding app2 retains
platform/app1 material, except the CA serial advances when a new certificate is issued.

No keys, passwords or certificates are committed. A CA private key on the target
is for the demo only: real production issues certificates elsewhere and delivers
them to the persistent component paths. Do not replace database passwords or the
CA during an upgrade. Keep private state outside releases and back it up.
