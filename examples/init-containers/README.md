# init-containers

Run `./examples/run.sh init-containers` after [the image setup](../README.md).

Two init containers share a manifest-defined PVC with the main container.
`first` writes the line `first`. `second` requires that line to exist before it adds
`second`. The main container checks both lines before it copies the result
to `/tmp/observed`. The host script reads and checks this copy.

Expected: exactly `first` and `second`, in that order. The main container
can pass the check only after both init containers. Missing or wrong content,
or a container that does not start, gives a non-zero exit. The PVC volume is cleaned up.
