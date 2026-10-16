# Generated secrets

Run `./examples/run.sh generated-secrets` from the repo root after the image
setup in [the examples README](../README.md).

The source declaration combines generation and delivery:

```yaml
SECRET_FILES:
  example-run-generated:
  - path: credentials/app
    generate: [API_TOKEN]
```

The first prepare creates `credentials/app/API_TOKEN`, a private 32-character
alphanumeric file. The Pod
receives the file through `SECRET_FILES` and `envFrom.secretRef`. The script
compares its bytes with the container environment, prepares again and requires
the original file and delivered value to remain unchanged after another play.

Expected result: PASS, with file mode 0600, directory mode 0700 and exact value
matches. No value or hash is printed. All generated files and Podman resources
are removed by the exit trap.
