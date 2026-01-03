from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from .telemetry import setup_telemetry
from .MetricsMiddleware import MetricsMiddleware
from .routers import post, user, auth, vote
import os

# Get OTLP endpoint from environment, default to otel-collector
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
setup_telemetry(otel_endpoint.replace("http://", ""))

app = FastAPI()

app.add_middleware(MetricsMiddleware)
FastAPIInstrumentor.instrument_app(app)
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
