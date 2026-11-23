from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="Box Packer",
        version="0.1.0",
        description="Computes how many shipping boxes are needed for a list of packages.",
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
