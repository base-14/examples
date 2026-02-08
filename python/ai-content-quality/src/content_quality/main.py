import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from content_quality.config import get_settings
from content_quality.middleware import MetricsMiddleware
from content_quality.models.requests import ContentRequest  # noqa: TC001
from content_quality.models.responses import ImproveResult, ReviewResult, ScoreResult  # noqa: TC001
from content_quality.services.analyzer import ContentAnalyzer
from content_quality.services.llm import create_llm
from content_quality.telemetry import instrument_fastapi, setup_telemetry


logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize OTel SDK + OpenInference BEFORE app creation
setup_telemetry(
    service_name=settings.service_name,
    otlp_endpoint=settings.otlp_endpoint,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.llm = create_llm(
        provider=settings.llm_provider,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key={
            "openai": settings.openai_api_key,
            "google": settings.google_api_key,
            "anthropic": settings.anthropic_api_key,
        }.get(settings.llm_provider, ""),
        timeout=settings.llm_timeout,
    )
    app.state.analyzer = ContentAnalyzer(app.state.llm)
    yield


app = FastAPI(title="AI Content Quality Agent", lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
instrument_fastapi(app)


def _record_error_on_span(exc: Exception) -> None:
    span = trace.get_current_span()
    if span.is_recording():
        span.record_exception(exc)
        span.set_attribute("error.type", type(exc).__name__)
        span.set_status(StatusCode.ERROR, str(exc))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    _record_error_on_span(exc)
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": settings.service_name}


@app.post("/review")
async def review_content(request: ContentRequest) -> ReviewResult:
    try:
        return await asyncio.wait_for(
            app.state.analyzer.review(request.content, request.content_type),
            timeout=settings.request_timeout,
        )
    except TimeoutError as exc:
        _record_error_on_span(exc)
        raise HTTPException(status_code=504, detail="Analysis timed out") from None
    except Exception as exc:
        _record_error_on_span(exc)
        logger.exception("Review analysis failed")
        raise HTTPException(status_code=502, detail="Analysis failed") from None


@app.post("/improve")
async def improve_content(request: ContentRequest) -> ImproveResult:
    try:
        return await asyncio.wait_for(
            app.state.analyzer.improve(request.content, request.content_type),
            timeout=settings.request_timeout,
        )
    except TimeoutError as exc:
        _record_error_on_span(exc)
        raise HTTPException(status_code=504, detail="Analysis timed out") from None
    except Exception as exc:
        _record_error_on_span(exc)
        logger.exception("Improve analysis failed")
        raise HTTPException(status_code=502, detail="Analysis failed") from None


@app.post("/score")
async def score_content(request: ContentRequest) -> ScoreResult:
    try:
        return await asyncio.wait_for(
            app.state.analyzer.score(request.content, request.content_type),
            timeout=settings.request_timeout,
        )
    except TimeoutError as exc:
        _record_error_on_span(exc)
        raise HTTPException(status_code=504, detail="Analysis timed out") from None
    except Exception as exc:
        _record_error_on_span(exc)
        logger.exception("Score analysis failed")
        raise HTTPException(status_code=502, detail="Analysis failed") from None
