#!/usr/bin/env python3
"""Fetch pinned, non-executable M4 model assets and verify upstream identities."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
import urllib.request

REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
REPOSITORY = "openai-community/gpt2"
SEMANTIC_REVISION = "9b63575ef42771a015060c964af2c3da4cf7c8ab"
# Git blob identities from the pinned Hugging Face repository tree; the large
# safetensors payload uses its LFS SHA-256. Never load pickle or remote code.
ASSETS = {
    "config.json": (665, "git", "10c66461e4c109db5a2196bff4bb59be30396ed8"),
    "generation_config.json": (124, "git", "3dc481ecc3b2c47a06ab4e20dba9d7f4b447bdf3"),
    "merges.txt": (456318, "git", "226b0752cac7789c48f0cb3ec53eda48b7be36cc"),
    "tokenizer.json": (1355256, "git", "4b988bccc9dc5adacd403c00b4704976196548f8"),
    "tokenizer_config.json": (26, "git", "be4d21d94f3b4687e5a54d84bf6ab46ed0f8defd"),
    "vocab.json": (1042301, "git", "1f1d9aaca301414e7f6c9396df506798ff4eb9a6"),
    "README.md": (8092, "git", "a16a55fda99d2f2e7b69cce5cf93ff4ad3049930"),
    "model.safetensors": (548105171, "sha256", "248dfc3911869ec493c76e65bf2fcf7f615828b0254c12b473182f0f81d3a707"),
}


def identity(path, kind="sha256"):
    digest = hashlib.sha1() if kind == "git" else hashlib.sha256()
    if kind == "git":
        digest.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url, target, size=None, kind="sha256", expected=None):
    def check(path):
        if size is not None and path.stat().st_size != size:
            raise ValueError(f"size mismatch: {target.name}")
        if expected and identity(path, kind) != expected:
            raise ValueError(f"identity mismatch: {target.name}")
    if target.exists():
        check(target)
        return
    # Only our just-created temporary file is removed on failure. An existing
    # mismatched target is never overwritten or silently accepted.
    for attempt in range(3):
        partial = None
        try:
            request = urllib.request.Request(url + ("&" if "?" in url else "?") +
                                             f"download=true&attempt={attempt}",
                                             headers={"User-Agent": "PocketAI-M4-pinned-fetch/1"})
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                partial = Path(output.name)
                with urllib.request.urlopen(request, timeout=120) as response:
                    while chunk := response.read(1 << 20):
                        output.write(chunk)
            check(partial)
            partial.replace(target)
            return
        except Exception:
            if partial is not None:
                partial.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("build/m4_model"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "repository": REPOSITORY, "revision": REVISION,
                "semantic_revision": SEMANTIC_REVISION, "license": "MIT", "files": {}}
    for name, (size, kind, expected) in ASSETS.items():
        url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"
        target = args.output / name
        fetch(url, target, size, kind, expected)
        manifest["files"][name] = {"url": url, "size": size, "upstream_kind": kind,
                                   "upstream_identity": expected, "sha256": identity(target)}
        print(f"M4 MODEL ASSET PASS {name} sha256={identity(target)}", flush=True)
    for filename, upstream, digest in (
        ("OPENAI_LICENSE", "LICENSE", "0dbeda4bc78823b1d67ec0ee414d8690ee4cad826bc9c147b215adc3af202436"),
        ("openai_model.py.txt", "src/model.py", "2ff5065f5cac3dc93065f8a3f36eb013e407972a80abcd4ee6b89a7138a0d5a6"),
    ):
        url = f"https://raw.githubusercontent.com/openai/gpt-2/{SEMANTIC_REVISION}/{upstream}"
        target = args.output / filename
        fetch(url, target, expected=digest)
        manifest["files"][filename] = {"url": url, "size": target.stat().st_size,
                                       "sha256": identity(target)}
    (args.output / "model_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("M4 MODEL FETCH PASS (asset identity only; model validation is separate)")


if __name__ == "__main__":
    main()
