package com.example.temporaltracing;

public class GreetingActivityImpl implements GreetingActivity {

    @Override
    public String composeGreeting(String greeting, String name) {
        return greeting + " " + name + "!";
    }
}
