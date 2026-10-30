"""Same-origin production host with protected API and public static assets."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .api import create_app


def create_site(settings=None, engine=None, static_directory=None):
    api = create_app(settings=settings, engine=engine)
    directory = Path(static_directory or os.environ.get('FRONTEND_DIST', '/app/frontend-dist'))
    if not (directory / 'index.html').is_file():
        raise RuntimeError('Frontend build missing; build the production container first.')

    @asynccontextmanager
    async def lifespan(_):
        async with api.router.lifespan_context(api):
            yield

    site = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    site.mount('/api', api)
    site.mount('/', StaticFiles(directory=directory, html=True))
    return site
