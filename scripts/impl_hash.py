import hashlib
from pathlib import Path


def compute_impl_hash(files: list[Path], base: Path | None = None) -> str:
    """Compute a deterministic sha256 over canonical bytes of all implementation files.

    Per the build spec section 2.4:
      1. Sort by repository-relative path.
      2. Normalize line endings to LF.
      3. Hash each file; concatenate `path:hash\n`; hash that.
    """
    base = base or Path.cwd()
    pairs: list[tuple[str, str]] = []
    for f in sorted(files, key=lambda p: str(p)):
        rel = str(f.relative_to(base)) if str(f).startswith(str(base)) else str(f)
        raw = f.read_bytes().replace(b"\r\n", b"\n")
        digest = hashlib.sha256(raw).hexdigest()
        pairs.append((rel, digest))

    aggregate = "".join(f"{p}:{d}\n" for p, d in pairs).encode("utf-8")
    return "sha256:" + hashlib.sha256(aggregate).hexdigest()
