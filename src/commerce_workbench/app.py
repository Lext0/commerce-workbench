from fastapi import FastAPI

from commerce_workbench import __version__


def create_app() -> FastAPI:
    app = FastAPI(title="Commerce Workbench", version=__version__)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app
