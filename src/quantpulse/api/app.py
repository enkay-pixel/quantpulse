from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from quantpulse import __version__
from quantpulse.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantPulse API",
        version=__version__,
        description=(
            "Read-only serving layer for the QuantPulse investing platform: "
            "prices, predictions, portfolio, model, and drift status. "
            "Educational project — not investment advice."
        ),
    )
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    return app


app = create_app()
