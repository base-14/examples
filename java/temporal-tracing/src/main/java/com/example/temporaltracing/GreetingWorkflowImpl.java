package com.example.temporaltracing;

import io.temporal.activity.ActivityOptions;
import io.temporal.workflow.Workflow;

import java.time.Duration;

public class GreetingWorkflowImpl implements GreetingWorkflow {

    private final GreetingActivity activity = Workflow.newActivityStub(
            GreetingActivity.class,
            ActivityOptions.newBuilder()
                    .setStartToCloseTimeout(Duration.ofSeconds(10))
                    .build());

    @Override
    public String greet(String name) {
        return activity.composeGreeting("Hello", name);
    }
}
