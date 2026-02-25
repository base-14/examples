package com.example.support.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.llm")
public record AppConfig(
    String provider,
    String modelCapable,
    String modelFast,
    String fallbackProvider,
    String fallbackModel,
    int maxTokens,
    double temperature
) {}
