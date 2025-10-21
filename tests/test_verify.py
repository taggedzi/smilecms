from pathlib import Path

from src.verify import verify_site


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_verify_site_detects_missing_internal_links_and_assets(tmp_path: Path) -> None:
    site_dir = tmp_path / "site"
    _write(
        site_dir / "index.html",
        """
        <html>
          <body>
            <a href="/about/">About Us</a>
            <img src="/media/photo.jpg" alt="Example" />
            <script src="./js/app.js"></script>
          </body>
        </html>
        """,
    )
    _write(site_dir / "js" / "app.js", "console.log('ok');")

    report = verify_site(site_dir)

    assert report.scanned_files == 1
    kinds = {issue.kind for issue in report.issues}
    targets = {issue.target for issue in report.issues}

    assert "missing-page" in kinds
    assert "missing-asset" in kinds
    assert "/about/" in targets
    assert "/media/photo.jpg" in targets


def test_verify_site_skips_external_and_fragments(tmp_path: Path) -> None:
    site_dir = tmp_path / "site"
    _write(
        site_dir / "index.html",
        """
        <html>
          <body>
            <a href="https://example.com">External</a>
            <a href="#details">Section</a>
            <img src="data:image/png;base64,abcd" />
          </body>
        </html>
        """,
    )

    report = verify_site(site_dir)

    assert report.scanned_files == 1
    assert report.issues == []


def test_verify_site_flags_out_of_bounds_references(tmp_path: Path) -> None:
    site_dir = tmp_path / "site"
    _write(
        site_dir / "index.html",
        """
        <html>
          <body>
            <a href="../secrets/admin.html">Forbidden</a>
          </body>
        </html>
        """,
    )

    report = verify_site(site_dir)

    assert report.issues
    assert report.issues[0].kind == "out-of-bounds"
