package com.example.temporaltracing;

import io.temporal.opentracing.OpenTracingClientInterceptor;
import io.temporal.opentracing.OpenTracingWorkerInterceptor;
import io.temporal.opentracing.OpenTracingOptions;
import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowClientOptions;
import io.temporal.client.WorkflowOptions;
import io.temporal.serviceclient.WorkflowServiceStubs;
import io.temporal.serviceclient.WorkflowServiceStubsOptions;
import io.temporal.worker.Worker;
import io.temporal.worker.WorkerFactory;
import io.temporal.worker.WorkerFactoryOptions;

public class App {

    static final String TASK_QUEUE = "tracing-example-queue";

    public static void main(String[] args) throws Exception {
        // Step 1: Read configuration from environment
        String temporalAddress = System.getenv().getOrDefault(
                "TEMPORAL_ADDRESS", "localhost:7233");

        // Step 2: Bootstrap OpenTelemetry and bridge to OpenTracing
        OpenTracingOptions otOptions = Tracing.buildTracingOptions();

        // Connect to Temporal server
        WorkflowServiceStubs service = WorkflowServiceStubs.newServiceStubs(
                WorkflowServiceStubsOptions.newBuilder()
                        .setTarget(temporalAddress)
                        .build());

        // Step 3: Register client interceptor
        WorkflowClient client = WorkflowClient.newInstance(
                service,
                WorkflowClientOptions.newBuilder()
                        .setInterceptors(new OpenTracingClientInterceptor(otOptions))
                        .build());

        // Step 4: Register worker interceptor
        WorkerFactory factory = WorkerFactory.newInstance(
                client,
                WorkerFactoryOptions.newBuilder()
                        .setWorkerInterceptors(new OpenTracingWorkerInterceptor(otOptions))
                        .build());

        Worker worker = factory.newWorker(TASK_QUEUE);
        worker.registerWorkflowImplementationTypes(GreetingWorkflowImpl.class);
        worker.registerActivitiesImplementations(new GreetingActivityImpl());

        factory.start();
        System.out.println("Worker started on task queue: " + TASK_QUEUE);

        // Execute a workflow to generate traces
        GreetingWorkflow workflow = client.newWorkflowStub(
                GreetingWorkflow.class,
                WorkflowOptions.newBuilder()
                        .setWorkflowId("greeting-" + System.currentTimeMillis())
                        .setTaskQueue(TASK_QUEUE)
                        .build());

        String result = workflow.greet("World");
        System.out.println("Workflow result: " + result);

        // Flush pending spans to the collector
        Tracing.getTracerProvider().forceFlush().join(10, java.util.concurrent.TimeUnit.SECONDS);
        System.out.println("Traces exported. Worker staying alive...");

        // Keep the worker running for additional workflow executions
        Thread.currentThread().join();
    }
}
