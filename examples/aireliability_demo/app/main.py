"""Main FastAPI application entrypoint for the AI Reliability Demo."""

from __future__ import annotations

from aireliability.api.app import api_app
from aireliability_demo.app.api.routes import demo_router

# Include demo routes into the production platform API app
api_app.include_router(demo_router)

app = api_app

if __name__ == "__main__":
    import uvicorn

    from aireliability_demo.app.config import DEFAULT_API_HOST, DEFAULT_API_PORT

    print(
        f"Starting AI Reliability Demo Server on http://{DEFAULT_API_HOST}:{DEFAULT_API_PORT}"
    )
    uvicorn.run(app, host=DEFAULT_API_HOST, port=DEFAULT_API_PORT)
