#!/usr/bin/env python3
"""Build and verify offline source-only Lambda evidence; never calls AWS."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

TARGETS = {
    "ocr": ("src/ParkinSync_OCR_Handler.py", "ParkinSync_OCR_Handler", 90),
    "iot": ("src/indoor_temp_logger.py", "ParkinSync_IndoorTemp_Logger", 120),
}


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.PIPE)


def trusted_source(repo: Path, target: str, commit: str) -> bytes:
    if target not in TARGETS:
        raise ValueError("target must be ocr or iot")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("expected commit must be a full 40-character SHA")
    if git(repo, "rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("repository HEAD differs from expected commit")
    source_path = TARGETS[target][0]
    path = repo / source_path
    if path.is_symlink() or not path.is_file():
        raise ValueError("source must be a regular file")
    source = git(repo, "show", f"{commit}:{source_path}")
    if path.read_bytes() != source:
        raise ValueError("working source differs from expected commit")
    return source


def package(source: bytes) -> bytes:
    stream = io.BytesIO()
    info = zipfile.ZipInfo("lambda_function.py", date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    # Stored bytes avoid compressor-version variation; artifacts remain small.
    info.compress_type = zipfile.ZIP_STORED
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(info, source)
    return stream.getvalue()


def receipt(target: str, commit: str, source: bytes, artifact: bytes) -> dict:
    source_path, function_name, timeout = TARGETS[target]
    digest = hashlib.sha256(artifact).digest()
    return {
        "schemaVersion": "parkinsync-offline-release/v1",
        "target": target, "functionName": function_name,
        "sourcePath": source_path, "sourceCommit": commit,
        "sourceSha256": hashlib.sha256(source).hexdigest(), "sourceBytes": len(source),
        "artifactName": "lambda.zip", "artifactSha256": digest.hex(),
        "localCodeSha256Base64": base64.b64encode(digest).decode(),
        "intendedSettings": {"runtime": "python3.12", "handler": "lambda_function.lambda_handler",
                             "timeoutSeconds": timeout, "memoryMB": 512},
        "dependencyScope": "source-only; external layers not included or verified",
        "deploymentStatus": "not_deployed", "awsReadback": None,
    }


def build(repo: Path, target: str, commit: str, output: Path) -> dict:
    repo = repo.resolve()
    output = output.absolute()
    if output.resolve().is_relative_to(repo):
        raise ValueError("release output must be outside the source repository")
    source = trusted_source(repo, target, commit)
    artifact = package(source)
    metadata = receipt(target, commit, source, artifact)
    # Reserve an absent directory. Existing evidence, including empty dirs or
    # symlinks, is never replaced; an interrupted pack remains visibly incomplete.
    output.mkdir()
    with (output / "lambda.zip").open("xb") as stream:
        stream.write(artifact)
    with (output / "receipt.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return metadata


def verify(repo: Path, target: str, commit: str, output: Path) -> dict:
    source = trusted_source(repo.resolve(), target, commit)
    artifact = (output / "lambda.zip").read_bytes()
    metadata = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
    if artifact != package(source) or metadata != receipt(target, commit, source, artifact):
        raise ValueError("release pack does not match trusted source and expected receipt")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--target", choices=tuple(TARGETS), required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        operation = build if args.operation == "build" else verify
        result = operation(args.repo, args.target, args.expected_commit, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Offline release pack failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
