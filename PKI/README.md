# Demo PKI

`dev/generate-certificates.sh [--root DIR] platform|identity|app1|app2|app3|help [DNS hostname]`
creates missing component material once. `PKI/generate.sh` forwards arguments to
that script. Dev uses build/dev; prod passes --root /var/lib/myproduct explicitly.
Component passwords, private keys and certificates live under
`<state>/<component>/credentials/`, with the same subdirectories and filenames
in dev and production. The shared CA stays in PKI/private. Platform owns the web TLS pair. Identity owns
its signing pair and shared demo-user passwords. Each app has a separate client pair. Database
passwords and session/API keys belong to deploy’s source-level `generate` declarations,
not this certificate script. See the PostgreSQL section in the root README for
state preflight, persistent paths, backup/recovery and manual config additions.

Identity receives only each client's public certificate; its private key and CA
certificate reach the own Todo through its Secret. All directories/files
are created privately. Repeating generation preserves existing nonempty files;
partial certificate/CA pairs and empty demo-user password files fail. Database
password validation happens in deploy’s lifecycle preflight. Adding app2 retains
platform/identity/app1 material, except the CA serial advances when a new certificate is issued.
app3 (backlog 71) gets only a client pair in `credentials/client/`; its public
trust chain `<state>/app3/cert/{root,ca}.crt` is a copy of the CA made by
`dev/demo-credentials.sh` in dev or by the operator on a target, not by this script.

No keys, passwords or certificates are committed. Explicit signing provisioning
can use the environment's existing CA or externally supplied credentials; new
local CAs still use development defaults until item 45a. Keep dev and production
roots/CAs separate. Do not replace database passwords or the CA during an upgrade.
Keep private state outside releases and back it up.

## External signing PFX consumers

`dev/generate-certificates.sh --root DIR --component ID --purpose signing --pfx`
adds explicit PFX provisioning without changing the demo commands above.
See [PFX credentials](../docs/PFX-CREDENTIALS.md) for password-file provisioning,
external PFX/PEM precedence, private output paths, Secret/mount examples and
pending runtime verification. Production can invoke it through the existing
stdin workflow; supported production CA configuration, tool delivery and renewal
remain backlog 45a/45b/45c. The current helper still uses development CA defaults
when no external CA/credential is supplied. CA keys must stay out of app Secrets.
