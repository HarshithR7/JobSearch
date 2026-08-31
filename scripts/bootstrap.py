"""One-command sanity check: run migrations, then smoke-import every
module that main.py and the Streamlit app depend on. Mirrors
Investment-Tracker's scripts/bootstrap.py."""

import argparse
import subprocess
import sys

from config import logger


def run_migrations() -> None:
    logger.info("Running alembic upgrade head")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)


def smoke_import() -> None:
    logger.info("Smoke-importing core modules")
    import database.models  # noqa: F401
    import collectors.ats_greenhouse  # noqa: F401
    import collectors.ats_lever  # noqa: F401
    import collectors.ats_ashby  # noqa: F401
    import collectors.ats_smartrecruiters  # noqa: F401
    import collectors.careers_generic  # noqa: F401
    import collectors.remoteok  # noqa: F401
    import collectors.hn_hiring  # noqa: F401
    import analysis.job_matcher  # noqa: F401
    import analysis.resume_tailor  # noqa: F401
    import analysis.prep_generator  # noqa: F401
    import analysis.gap_advisor  # noqa: F401
    logger.info("Smoke import OK")


def install_deps() -> None:
    logger.info("Installing dependencies from requirements.txt")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-deps", action="store_true")
    args = parser.parse_args()

    if args.install_deps:
        install_deps()
    run_migrations()
    smoke_import()
    logger.info("Bootstrap complete")


if __name__ == "__main__":
    main()
