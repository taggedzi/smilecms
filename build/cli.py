import typer
from rich.console import Console

from .config import Config, load_config
from .ingest import load_documents
from .manifests import ManifestGenerator, write_manifest_pages
from .media import collect_media_plan
from .validation import DocumentValidationError

console = Console()
app = typer.Typer(help="SmileCMS static publishing toolkit.")

@app.command()
def build(config_path: str = "smilecms.yml") -> None:
    """Run a full rebuild of site artifacts."""
    config = _load(config_path)
    try:
        documents = load_documents(config)
    except DocumentValidationError as error:
        console.print(f"[bold red]Validation failed[/]: {error}")
        raise typer.Exit(code=1)

    count = len(documents)
    generator = ManifestGenerator()
    pages = generator.build_pages(documents, prefix="content")
    manifest_dir = config.output_dir / "manifests"
    written = write_manifest_pages(pages, manifest_dir)
    media_plan = collect_media_plan(documents, config)

    console.print(f"[bold green]Loaded[/] {count} document(s).")
    console.print(
        f"[bold green]Generated[/] {len(written)} manifest page(s) "
        f"under {manifest_dir}"
    )
    console.print(
        f"[bold green]Planned[/] {len(media_plan.tasks)} media derivative task(s) "
        f"across {media_plan.asset_count} asset(s)."
    )

@app.command()
def preview(config_path: str = "smilecms.yml") -> None:
    """Launch local preview server (stub)."""
    config = _load(config_path)
    console.print(f"[bold yellow]TODO[/]: start preview for {config.project_name}")

@app.command()
def clean(config_path: str = "smilecms.yml") -> None:
    """Remove generated artifacts (stub)."""
    config = _load(config_path)
    console.print(f"[bold red]TODO[/]: clean artifacts for {config.project_name}")

def _load(path: str) -> Config:
    try:
        return load_config(path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"Config file not found: {path}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
