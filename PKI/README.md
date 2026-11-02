# Certificate provisioning

Use `dev/generate-certificates.sh` directly. The shipped demo is provisioned by
`dev/demo-credentials.sh`; generic deployment never provisions the PKI implicitly.

The helper supports an explicit `--root`, `--ca-subject`, `--ca-days` and
`--cert-days`, and retains complete existing credentials and the CA. An explicit
CA subject must match a retained CA. Keep DEV and PROD roots separate and keep
CA private keys out of component Secrets and release bundles.

See [PFX credentials](../docs/PFX-CREDENTIALS.md) for supported commands,
external credentials, private password files, paths and production CA options.
Tool delivery and renewal remain backlog 45b/45c; configurable CA provisioning
(45a) is implemented. Runtime deployment steps are in the
[production manual](../docs/PRODUCTION-INSTALL.md).

No private keys, passwords or certificates belong in this directory in Git.
