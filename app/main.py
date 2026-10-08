from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db import Base, engine
import app.models  # noqa: F401
from app.routers.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Bulk Certificate Generator",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(jobs_router)


@app.get("/health")
def health():
    return {"status": "ok"}
