import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from .MetricsMiddleware import MetricsMiddleware
from .routers import auth, post, user, vote
from .telemetry import setup_telemetry

setup_telemetry()

app = FastAPI()

app.add_middleware(MetricsMiddleware)
RequestsInstrumentor().instrument()

origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(post.router)
app.include_router(user.router)
app.include_router(auth.router)
app.include_router(vote.router)


@app.get("/")
def root():
    return {"message": "Hello World"}
