import argparse
from dataclasses import replace
from pathlib import Path

import uvicorn

from commerce_workbench.app import create_app
from commerce_workbench.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Commerce Workbench")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    try:
        settings = Settings.from_environment()
        overrides = {key: value for key, value in vars(args).items() if value is not None}
        settings = replace(settings, **overrides)
    except ValueError as exc:
        parser.error(str(exc))
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
