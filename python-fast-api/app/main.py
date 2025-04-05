from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from .telemetry import setup_telemetry
from .MetricsMiddleware import MetricsMiddleware
from .routers import post, user, auth, vote

setup_telemetry("0.0.0.0:4318")

app = FastAPI()

app.add_middleware(MetricsMiddleware)
FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(post.router)
app.include_router(user.router)
app.include_router(auth.router)
app.include_router(vote.router)


@app.get("/")
def root():
    return {"message": "Hello World"}
