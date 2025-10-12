import typer
from rich.console import Console
from .config import load_config, Config

console = Console()
app = typer.Typer(help="SmileCMS static publishing toolkit.")

@app.command()
def build(config_path: str = "smilecms.yml") -> None:
    """Run a full rebuild of site artifacts."""
    config = _load(config_path)
    console.print(f"[bold green]TODO[/]: run build pipeline for {config.project_name}")

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
