"""CLI entry point (spec section 15)."""
import typer

from app.core.config import config_report, get_settings

app = typer.Typer(help="FinShield command line")


@app.command("config-check")
def config_check() -> None:
    """Redacted configuration validation."""
    rep = config_report(get_settings())
    for k, v in rep.items():
        typer.echo(f"{k}: {v}")
    raise typer.Exit(0 if all(v == "configured" for v in rep.values()) else 1)


@app.command("db-upgrade")
def db_upgrade() -> None:
    """Create/upgrade application tables (SQLAlchemy metadata; Alembic migrations are still to do)."""
    from app.db import backend_name, init_db
    init_db()
    typer.echo(f"tables ready on {backend_name()}")


@app.command("bootstrap-admin")
def bootstrap_admin() -> None:
    """Interactive masked entry of the first admin."""
    from app.bootstrap import bootstrap_admin as f
    f()


@app.command("seed-users")
def seed_users() -> None:
    """Create demo users with random passwords (written to artifacts/demo_credentials.txt) + initial promotion."""
    from app.bootstrap import CRED_FILE, seed_users as f
    made = f()
    typer.echo(f"created {len(made)} users" + (f"; credentials in {CRED_FILE}" if made else " (already existed)"))


@app.command("dataset-build")
def dataset_build(customers: int = 600, seed: int = 42) -> None:
    from app.ml.pipeline import generate_dataset
    generate_dataset(customers, seed)


@app.command("train")
def train() -> None:
    """Train exactly LR/RF/HGB on the stored dataset."""
    from app.ml.pipeline import train_models
    train_models()


@app.command("cluster")
def cluster() -> None:
    from app.ml.pipeline import recluster
    recluster()


if __name__ == "__main__":
    app()
