# Offline Lambda release packs

`scripts/lambda_release_pack.py` retains a source-only ZIP and JSON receipt outside
the source repository. It never calls AWS, installs dependencies or changes
`deploy.sh`. Choose `ocr` or `iot` explicitly and provide the full expected HEAD SHA:

```bash
python3 scripts/lambda_release_pack.py build --target ocr \
  --expected-commit <full-40-character-commit> --output /tmp/parkinsync-ocr-pack
python3 scripts/lambda_release_pack.py verify --target ocr \
  --expected-commit <same-full-commit> --output /tmp/parkinsync-ocr-pack
```

Use a new output directory for every build. Existing directories and symlinks are
rejected; interrupted builds remain incomplete and must fail verification. Keep
pack directories out of source control. The receipt binds target, source commit,
source hash, ZIP hash and intended default settings. ZIP bytes use a fixed timestamp
and stored source bytes, so repeated builds of the same source are identical.
Verification compares both files with source read from the expected Git commit;
changing an artifact and recomputing its receipt does not establish that identity.
The local repository is the trust anchor; this is not a signed provenance system.

`--repo` can identify a separate checkout. Its HEAD must equal the expected commit,
and the selected working source must match that commit and be a regular file.
Other working files are outside the pack and are not certified by the receipt.

The pack contains only `lambda_function.py`. External Lambda layers and runtime
compatibility are not included or verified. The receipt's settings are local
intended defaults, not an AWS observation. `deploymentStatus` is `not_deployed`;
there is no deployed readback, version, trigger qualifier or acceptance result.
A pack is not deployment or rollback authorization. The existing reviewed release
path and production approval remain necessary, including trigger-specific recovery
and actual deployed digest/configuration checks.
