#!/usr/bin/env python3

import asyncio
import aiohttp
import json
import logging
import random
import time
from datetime import datetime
from opentelemetry import trace, metrics, _logs
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
import os

# Configuration
BASE_URL = os.getenv('TARGET_URL', 'http://web:3000')
OTEL_ENDPOINT = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://otel-collector:4317')
SERVICE_NAME = os.getenv('OTEL_SERVICE_NAME', 'hotel-food-loadgen')
REQUESTS_PER_SECOND = int(os.getenv('REQUESTS_PER_SECOND', '2'))
DURATION_SECONDS = int(os.getenv('DURATION_SECONDS', '300'))

# Configure OpenTelemetry
def configure_otel():
    # Trace configuration
    trace.set_tracer_provider(TracerProvider())
    tracer_provider = trace.get_tracer_provider()
    
    span_processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
    )
    tracer_provider.add_span_processor(span_processor)
    
    # Metrics configuration
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=OTEL_ENDPOINT, insecure=True),
        export_interval_millis=5000
    )
    metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))
    
    # Logs configuration
    logger_provider = LoggerProvider()
    _logs.set_logger_provider(logger_provider)
    
    log_processor = BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=OTEL_ENDPOINT, insecure=True)
    )
    logger_provider.add_log_record_processor(log_processor)
    
    # Instrument HTTP client
    AioHttpClientInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)

# Initialize telemetry
configure_otel()

# Get telemetry objects
tracer = trace.get_tracer(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)

# Setup structured logging with OTEL handler
handler = LoggingHandler(logger_provider=_logs.get_logger_provider())
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Metrics
request_counter = meter.create_counter(
    name="loadgen_requests_total",
    description="Total number of requests made"
)

response_time_histogram = meter.create_histogram(
    name="loadgen_response_time_seconds",
    description="Response time distribution"
)

error_counter = meter.create_counter(
    name="loadgen_errors_total", 
    description="Total number of errors"
)

# User scenarios with realistic weights
USER_SCENARIOS = [
    {"name": "browse_hotels", "weight": 0.3},
    {"name": "view_hotel_foods", "weight": 0.25},
    {"name": "user_signup_login", "weight": 0.1},
    {"name": "place_order", "weight": 0.2},
    {"name": "view_order_history", "weight": 0.15}
]

class LoadGenerator:
    def __init__(self):
        self.session = None
        self.users = []
        self.hotels = []
        self.foods = []
        
    async def start(self):
        self.session = aiohttp.ClientSession()
        await self.initialize_data()
        
    async def stop(self):
        if self.session:
            await self.session.close()
            
    async def initialize_data(self):
        """Get initial data from the app"""
        with tracer.start_as_current_span("loadgen.initialize") as span:
            try:
                # Get hotels
                async with self.session.get(f"{BASE_URL}/hotels") as resp:
                    if resp.status == 200:
                        # Parse HTML to extract hotel IDs (simplified)
                        self.hotels = list(range(1, 6))  # Assume 5 hotels
                        span.set_attribute("hotels.count", len(self.hotels))
                        logger.info(f"Initialized with {len(self.hotels)} hotels")
                        
                # Get some food items
                for hotel_id in self.hotels[:2]:  # Sample first 2 hotels
                    async with self.session.get(f"{BASE_URL}/hotels/{hotel_id}") as resp:
                        if resp.status == 200:
                            # Assume each hotel has foods with IDs
                            hotel_foods = list(range((hotel_id-1)*5 + 1, hotel_id*5 + 1))
                            self.foods.extend(hotel_foods)
                            
                span.set_attribute("foods.count", len(self.foods))
                logger.info(f"Initialized with {len(self.foods)} food items")
                
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"Failed to initialize data: {e}")
                
    async def create_user(self):
        """Create a new user and return credentials"""
        with tracer.start_as_current_span("loadgen.create_user") as span:
            user_id = random.randint(10000, 99999)
            user_data = {
                "user[name]": f"LoadTest User {user_id}",
                "user[email]": f"loadtest{user_id}@example.com", 
                "user[password]": "password123",
                "user[password_confirmation]": "password123"
            }
            
            try:
                start_time = time.time()
                async with self.session.post(f"{BASE_URL}/signup", data=user_data) as resp:
                    response_time = time.time() - start_time
                    
                    span.set_attributes({
                        "user.email": user_data["user[email]"],
                        "http.status_code": resp.status,
                        "response_time": response_time
                    })
                    
                    request_counter.add(1, {"endpoint": "/signup", "method": "POST"})
                    response_time_histogram.record(response_time, {"endpoint": "/signup"})
                    
                    if resp.status in [200, 302]:  # Success or redirect
                        logger.info(f"Created user: {user_data['user[email]']}")
                        return user_data["user[email]"], user_data["user[password]"]
                    else:
                        logger.warning(f"User creation failed with status {resp.status}")
                        error_counter.add(1, {"endpoint": "/signup", "error": "http_error"})
                        return None, None
                        
            except Exception as e:
                span.record_exception(e)
                error_counter.add(1, {"endpoint": "/signup", "error": "exception"})
                logger.error(f"Exception creating user: {e}")
                return None, None
                
    async def login_user(self, email, password):
        """Login user and maintain session"""
        with tracer.start_as_current_span("loadgen.login_user") as span:
            login_data = {
                "email": email,
                "password": password
            }
            
            try:
                start_time = time.time()
                async with self.session.post(f"{BASE_URL}/login", data=login_data) as resp:
                    response_time = time.time() - start_time
                    
                    span.set_attributes({
                        "user.email": email,
                        "http.status_code": resp.status,
                        "response_time": response_time
                    })
                    
                    request_counter.add(1, {"endpoint": "/login", "method": "POST"})
                    response_time_histogram.record(response_time, {"endpoint": "/login"})
                    
                    if resp.status in [200, 302]:
                        logger.info(f"User logged in: {email}")
                        return True
                    else:
                        error_counter.add(1, {"endpoint": "/login", "error": "http_error"})
                        return False
                        
            except Exception as e:
                span.record_exception(e)
                error_counter.add(1, {"endpoint": "/login", "error": "exception"})
                logger.error(f"Exception logging in: {e}")
                return False
                
    async def browse_hotels(self):
        """Browse hotels scenario"""
        with tracer.start_as_current_span("loadgen.scenario.browse_hotels") as span:
            try:
                start_time = time.time()
                async with self.session.get(f"{BASE_URL}/hotels") as resp:
                    response_time = time.time() - start_time
                    
                    span.set_attributes({
                        "http.status_code": resp.status,
                        "response_time": response_time,
                        "scenario": "browse_hotels"
                    })
                    
                    request_counter.add(1, {"endpoint": "/hotels", "method": "GET"})
                    response_time_histogram.record(response_time, {"endpoint": "/hotels"})
                    
                    if resp.status == 200:
                        logger.info("Successfully browsed hotels")
                    else:
                        error_counter.add(1, {"endpoint": "/hotels", "error": "http_error"})
                        
            except Exception as e:
                span.record_exception(e)
                error_counter.add(1, {"endpoint": "/hotels", "error": "exception"})
                logger.error(f"Exception browsing hotels: {e}")
                
    async def view_hotel_foods(self):
        """View foods for a specific hotel"""
        with tracer.start_as_current_span("loadgen.scenario.view_hotel_foods") as span:
            if not self.hotels:
                return
                
            hotel_id = random.choice(self.hotels)
            span.set_attribute("hotel.id", hotel_id)
            
            try:
                start_time = time.time()
                async with self.session.get(f"{BASE_URL}/hotels/{hotel_id}") as resp:
                    response_time = time.time() - start_time
                    
                    span.set_attributes({
                        "http.status_code": resp.status,
                        "response_time": response_time,
                        "scenario": "view_hotel_foods"
                    })
                    
                    request_counter.add(1, {"endpoint": "/hotels/:id", "method": "GET"})
                    response_time_histogram.record(response_time, {"endpoint": "/hotels/:id"})
                    
                    if resp.status == 200:
                        logger.info(f"Successfully viewed foods for hotel {hotel_id}")
                    else:
                        error_counter.add(1, {"endpoint": "/hotels/:id", "error": "http_error"})
                        
            except Exception as e:
                span.record_exception(e)
                error_counter.add(1, {"endpoint": "/hotels/:id", "error": "exception"})
                logger.error(f"Exception viewing hotel foods: {e}")
                
    async def user_signup_login(self):
        """Complete user signup and login flow"""
        with tracer.start_as_current_span("loadgen.scenario.user_signup_login") as span:
            email, password = await self.create_user()
            if email and password:
                await asyncio.sleep(1)  # Realistic delay
                success = await self.login_user(email, password)
                span.set_attribute("signup_login.success", success)
                if success:
                    self.users.append({"email": email, "password": password})
                    
    async def place_order(self):
        """Place an order for food"""
        with tracer.start_as_current_span("loadgen.scenario.place_order") as span:
            if not self.foods:
                return
                
            # Ensure we have a logged-in user
            if not self.users:
                await self.user_signup_login()
                if not self.users:
                    return
                    
            food_id = random.choice(self.foods)
            quantity = random.randint(1, 3)
            
            span.set_attributes({
                "food.id": food_id,
                "order.quantity": quantity,
                "scenario": "place_order"
            })
            
            # First get the order form
            try:
                async with self.session.get(f"{BASE_URL}/foods/{food_id}/order") as resp:
                    if resp.status != 200:
                        error_counter.add(1, {"endpoint": "/foods/:id/order", "error": "http_error"})
                        return
                        
                # Then place the order
                order_data = {
                    "order[quantity]": str(quantity)
                }
                
                start_time = time.time()
                async with self.session.post(f"{BASE_URL}/foods/{food_id}/order", data=order_data) as resp:
                    response_time = time.time() - start_time
                    
                    span.set_attributes({
                        "http.status_code": resp.status,
                        "response_time": response_time
                    })
                    
                    request_counter.add(1, {"endpoint": "/foods/:id/order", "method": "POST"})
                    response_time_histogram.record(response_time, {"endpoint": "/foods/:id/order"})
                    
                    if resp.status in [200, 302]:
                        logger.info(f"Successfully placed order for food {food_id}, quantity {quantity}")
                    else:
                        error_counter.add(1, {"endpoint": "/foods/:id/order", "error": "http_error"})
                        
            except Exception as e:
                span.record_exception(e)
                error_counter.add(1, {"endpoint": "/foods/:id/order", "error": "exception"})
                logger.error(f"Exception placing order: {e}")
                
    async def view_order_history(self):
        """View user's order history"""
        with tracer.start_as_current_span("loadgen.scenario.view_order_history") as span:
            try:
                start_time = time.time()
                async with self.session.get(f"{BASE_URL}/orders") as resp:
                    response_time = time.time() - start_time
                    
                    span.set_attributes({
                        "http.status_code": resp.status,
                        "response_time": response_time,
                        "scenario": "view_order_history"
                    })
                    
                    request_counter.add(1, {"endpoint": "/orders", "method": "GET"})
                    response_time_histogram.record(response_time, {"endpoint": "/orders"})
                    
                    if resp.status == 200:
                        logger.info("Successfully viewed order history")
                    else:
                        error_counter.add(1, {"endpoint": "/orders", "error": "http_error"})
                        
            except Exception as e:
                span.record_exception(e)
                error_counter.add(1, {"endpoint": "/orders", "error": "exception"})
                logger.error(f"Exception viewing order history: {e}")
                
    async def execute_scenario(self):
        """Execute a weighted random scenario"""
        scenario = random.choices(
            [s["name"] for s in USER_SCENARIOS],
            weights=[s["weight"] for s in USER_SCENARIOS],
            k=1
        )[0]
        
        scenario_method = getattr(self, scenario)
        await scenario_method()
        
    async def generate_load(self):
        """Main load generation loop"""
        logger.info(f"Starting load generation: {REQUESTS_PER_SECOND} RPS for {DURATION_SECONDS}s")
        
        end_time = time.time() + DURATION_SECONDS
        request_interval = 1.0 / REQUESTS_PER_SECOND
        
        while time.time() < end_time:
            start_time = time.time()
            
            # Execute scenario
            await self.execute_scenario()
            
            # Maintain request rate
            elapsed = time.time() - start_time
            sleep_time = max(0, request_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                
        logger.info("Load generation completed")

async def main():
    loadgen = LoadGenerator()
    
    try:
        await loadgen.start()
        await loadgen.generate_load()
    finally:
        await loadgen.stop()
        
    # Allow final telemetry export
    await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())