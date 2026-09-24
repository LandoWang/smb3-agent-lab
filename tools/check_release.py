"""Fail closed on forbidden publication artifacts and broken local doc links.

A heuristic guard, not a guarantee that arbitrary future files contain no secrets.
"""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {".nes", ".rom", ".state", ".gz", ".zip", ".pt", ".pth", ".safetensors",
             ".pem", ".key", ".npz", ".bin"}
SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")
PRIVATE = re.compile("/" + "Users" + r"/[^/\s]+/|" + "/" + "home" + r"/[^/\s]+/|ssh-rsa\s+[A-Za-z0-9+/]+")
LINK = re.compile(r"!?\[[^\]]*\]\(([^\s)]+)\)")


def inspect_file(path):
    rel = path.relative_to(ROOT)
    if path.is_symlink():
        return [f"Symlink excluded: {rel}"]
    if path.suffix.lower() in FORBIDDEN or path.name.startswith(".env"):
        return [f"Forbidden artifact: {rel}"]
    data = path.read_bytes()
    if data.startswith(b"NES\x1a") or len(data) > 20_000_000:
        return [f"ROM signature or oversized file: {rel}"]
    if path.suffix in {".png", ".mp4"}:
        return []
    text = data.decode("utf-8")
    errors = []
    if SECRET.search(text) or PRIVATE.search(text):
        errors.append(f"Possible secret/private path: {rel}")
    if path.suffix == ".md":
        for target in LINK.findall(text):
            if target.startswith(("https://", "http://", "#", "mailto:")):
                continue
            if not (path.parent / target.split("#")[0]).exists():
                errors.append(f"Broken local link in {rel}: {target}")
    return errors


def check():
    errors = []
    for path in ROOT.rglob("*"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.is_file() or path.is_symlink():
            errors.extend(inspect_file(path))
    sums = ROOT / "assets/SHA256SUMS"
    if sums.exists():
        for line in sums.read_text().splitlines():
            expected, name = line.split("  ", 1)
            if hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest() != expected:
                errors.append(f"Asset hash mismatch: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Release artifact, private-path, credential-pattern, link and media-hash checks passed.")


if __name__ == "__main__":
    check()
