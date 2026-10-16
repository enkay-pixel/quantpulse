from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse

from quantpulse import __version__
from quantpulse.api.routes import router

#: FastAPI's own request-validation schemas; their fields are FastAPI's to describe.
_BUILT_IN_SCHEMAS = {"HTTPValidationError", "ValidationError"}


def describe_fields(spec: dict[str, Any]) -> dict[str, Any]:
    """Give every response field a plain title and description from the glossary.

    The API's /docs page is generated from the response models, which name fields the way the
    code does (`alpha_t_stat`, `psi`). Read from the glossary here, the page explains each one in
    the same words the dashboard uses, and a field without an entry is caught by a test rather
    than published unexplained.
    """
    from quantpulse import glossary

    terms = glossary.load()
    for name, schema in spec.get("components", {}).get("schemas", {}).items():
        if name in _BUILT_IN_SCHEMAS:
            continue
        for field, prop in schema.get("properties", {}).items():
            entry = terms.get(field)
            if entry is not None:
                prop["title"] = entry.label
                prop["description"] = entry.describe()
    return spec


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantPulse API",
        version=__version__,
        description=(
            "Read-only data behind the QuantPulse dashboard: prices, the model's forecasts, the "
            "paper books and how they performed, the options data, and the research pages. Every "
            "field below is explained in plain words, in the same terms the dashboard uses. "
            "An educational project — nothing here is investment advice."
        ),
    )
    app.include_router(router)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            spec = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
            app.openapi_schema = describe_fields(spec)
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    return app


app = create_app()
