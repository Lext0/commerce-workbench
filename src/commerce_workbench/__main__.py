import argparse

import uvicorn

from commerce_workbench.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Commerce Workbench")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
