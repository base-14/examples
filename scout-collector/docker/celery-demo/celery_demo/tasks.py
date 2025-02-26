from celery import Celery
import os
import time
from opentelemetry import trace
from .telemetry import init_celery_tracing
from opentelemetry.instrumentation.celery import CeleryInstrumentor

from .config import OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_TRACES_ENDPOINT


RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")

celery = Celery(
    'tasks',
    broker=f'amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}//',
    backend=f'redis://{REDIS_HOST}:6379/0'
)

# Initialize Celery tracing
init_celery_tracing(celery)

@celery.task
def process_task(task_id: int):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("process_task") as span:
        span.set_attribute("task_id", task_id)
        # Simulate some heavy processing
        with tracer.start_span("heavy_processing") as processing_span:
            time.sleep(10)
            processing_span.set_attribute("processing_time", 10)

        span.set_attribute("status", "completed")
        span.end()
        return {"task_id": task_id, "status": "completed"}
