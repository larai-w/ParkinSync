#!/usr/bin/env python3
"""Reject missing, changed, or unconstrained application/FHIR dependencies."""
from importlib.metadata import distributions
from pathlib import Path
import re
import sys

TOOLCHAIN = {"pip", "setuptools", "wheel"}
SNAPSHOT = Path(__file__).resolve().parents[1] / "constraints-python312.txt"


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def read_snapshot(path):
    expected = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)", line)
        if not match:
            raise ValueError(f"line {number}: expected one exact package==version pin")
        name, version = normalize(match[1]), match[2]
        if name in expected or name in TOOLCHAIN:
            raise ValueError(f"line {number}: duplicate or toolchain package {name}")
        expected[name] = version
    if not expected:
        raise ValueError("dependency snapshot is empty")
    return expected


def differences(expected, installed):
    actual = {normalize(name): version for name, version in installed.items()
              if normalize(name) not in TOOLCHAIN}
    errors = []
    for name, version in sorted(expected.items()):
        if name not in actual:
            errors.append(f"missing: {name}=={version}")
        elif actual[name] != version:
            errors.append(f"changed: {name}: expected {version}, installed {actual[name]}")
    errors.extend(f"unconstrained: {name}=={actual[name]}" for name in sorted(actual.keys() - expected.keys()))
    return errors


def main():
    try:
        expected = read_snapshot(SNAPSHOT)
    except (OSError, ValueError) as error:
        print(f"Invalid dependency snapshot: {error}", file=sys.stderr)
        return 1
    installed = {item.metadata["Name"]: item.version for item in distributions()}
    errors = differences(expected, installed)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Dependency snapshot matches ({len(expected)} packages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
