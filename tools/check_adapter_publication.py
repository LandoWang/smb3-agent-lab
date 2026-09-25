"""Heuristic PII/deployment screen for the staged/tracked public adapter subset.

No scanner proves the absence of all sensitive content. Also review the diff.
Print only file names/rule names, not candidate secret values.
"""
import ipaddress
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
RULES={
    'private_home_path':re.compile(r'/(?:Users|home)/[^/\s]+/'),
    'private_mount':re.compile(r'/(?:mnt|dev/shm)/'),
    'email':re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
    'ssh_key':re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|ssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/]+'),
    'credential':re.compile(r'sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'),
    'azure_instance':re.compile(r'https://[A-Za-z0-9-]+\.openai\.azure\.com'),
    'engine_launch_config':re.compile(r'--(?:gpu-memory-utilization|kv-cache-memory|max-model-len|tensor-parallel-size)\b'),
}
IPV4=re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')
PRIVATE_DIRS={'sessions','runtime','test-tmp','validation','roms','models','states','memory'}


def check():
    files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    files=[f for f in files if f and (f.startswith('adapter/') or f.startswith('docs/adapter-'))]
    if not files: raise SystemExit('Stage the adapter files before publication scanning.')
    errors=[]
    for name in files:
        path=ROOT/name
        if PRIVATE_DIRS.intersection(path.relative_to(ROOT).parts) or path.is_symlink():
            errors.append((name,'private_artifact_or_symlink'));continue
        try: value=path.read_text()
        except (UnicodeDecodeError,OSError):
            errors.append((name,'nontext_or_unreadable'));continue
        for rule,pattern in RULES.items():
            if pattern.search(value): errors.append((name,rule))
        for match in IPV4.finditer(value):
            try: address=ipaddress.ip_address(match.group())
            except ValueError: continue
            if not address.is_loopback: errors.append((name,'nonloopback_ip'))
    if errors:
        raise SystemExit('\n'.join(f'{name}: {rule}' for name,rule in errors))
    print(f'Adapter PII/deployment heuristic checks passed: {len(files)} text files.')


if __name__=='__main__': check()
