package com.example.temporaltracing;

import io.temporal.activity.ActivityInterface;
import io.temporal.activity.ActivityMethod;

@ActivityInterface
public interface GreetingActivity {

    @ActivityMethod
    String composeGreeting(String greeting, String name);
}
