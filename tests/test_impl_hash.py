from pathlib import Path
from scripts.impl_hash import compute_impl_hash


def test_impl_hash_is_deterministic(tmp_path: Path):
    a = tmp_path / "a.yaml"; a.write_text("hello\n")
    b = tmp_path / "b.yaml"; b.write_text("world\n")
    h1 = compute_impl_hash([a, b])
    h2 = compute_impl_hash([b, a])     # order-independent (sort by path)
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert len(h1) == 71


def test_impl_hash_changes_with_content(tmp_path: Path):
    a = tmp_path / "a.yaml"; a.write_text("hello\n")
    h1 = compute_impl_hash([a])
    a.write_text("goodbye\n")
    h2 = compute_impl_hash([a])
    assert h1 != h2
