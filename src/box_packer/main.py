from fastapi import FastAPI

from box_packer.api.errors import register_error_handlers
from box_packer.api.routes import router
from box_packer.catalogue import Catalogue, load_catalogue


def create_app(catalogue: Catalogue | None = None) -> FastAPI:
    """Build the app. Without an explicit catalogue, boxes.json is loaded (once) here,
    so an invalid catalogue stops the service at startup rather than mid-request."""
    app = FastAPI(
        title="Box Packer",
        version="0.1.0",
        description="Computes how many shipping boxes are needed for a list of packages.",
    )
    app.state.catalogue = catalogue if catalogue is not None else load_catalogue()
    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
