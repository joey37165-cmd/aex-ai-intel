from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import stat
import tempfile
from pathlib import Path


def configure_admin_token(env_path: Path) -> str:
    token = secrets.token_urlsafe(32)
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = existing.splitlines()
    replacement = f"ADMIN_API_TOKEN={token}"
    replaced = False
    updated: list[str] = []
    for line in lines:
        if line.startswith("ADMIN_API_TOKEN="):
            if not replaced:
                updated.append(replacement)
                replaced = True
            continue
        updated.append(line)
    if not replaced:
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(replacement)

    env_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{env_path.name}.", dir=env_path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(updated).rstrip() + "\n")
        os.replace(temporary_path, env_path)
        if os.name != "nt":
            env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    finally:
        temporary_path.unlink(missing_ok=True)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成并配置模板管理 API Token")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()
    fingerprint = configure_admin_token(args.env)
    print(f"ADMIN_API_TOKEN 已配置，指纹: {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
