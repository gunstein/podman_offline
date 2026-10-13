# basic

Run `./examples/run.sh basic` from the repo root after the image setup in
[the overview](../README.md). The default port is 18080; use `EXAMPLE_PORT=18081`
if it is taken.

Tests a ConfigMap through `envFrom`, strings and integers through placeholders,
ConfigMap values as strings, plus `hostPort` and `hostIP: 127.0.0.1`.
BusyBox httpd listens on container port 8080. The config key is still called
`HTTPS_PORT` because deploy requires it, but this test server uses plain HTTP.

Expected: `curl` gets `hello from config|42|18080`, the environment variables match,
and `podman port` shows exactly `127.0.0.1:18080`. When the port is overridden,
the expected response changes accordingly. The script ends with PASS and exit 0.
