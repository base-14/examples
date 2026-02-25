package com.example.support.llm;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;

@Component
public class Pricing {

    private static final Logger log = LoggerFactory.getLogger(Pricing.class);
    private static final double FALLBACK_INPUT = 3.0;
    private static final double FALLBACK_OUTPUT = 15.0;
    private static final double PER_MILLION = 1_000_000.0;

    private Map<String, ModelPricing> models = Map.of();

    @JsonIgnoreProperties(ignoreUnknown = true)
    record PricingFile(String version, Map<String, ModelPricing> models) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ModelPricing(String provider, double input, double output) {}

    @PostConstruct
    void loadPricing() {
        var objectMapper = new ObjectMapper();
        String pricingFile = System.getenv("PRICING_FILE");
        try {
            InputStream stream;
            if (pricingFile != null && Files.exists(Path.of(pricingFile))) {
                stream = Files.newInputStream(Path.of(pricingFile));
                log.info("Loaded pricing from {}", pricingFile);
            } else {
                stream = getClass().getClassLoader().getResourceAsStream("pricing.json");
                if (stream == null) {
                    log.warn("No pricing.json found, using fallback pricing");
                    return;
                }
                log.info("Loaded pricing from classpath");
            }
            var file = objectMapper.readValue(stream, PricingFile.class);
            this.models = file.models();
            log.info("Loaded pricing v{} with {} models", file.version(), models.size());
        } catch (IOException e) {
            log.warn("Failed to load pricing.json: {}", e.getMessage());
        }
    }

    public double calculateCost(String model, int inputTokens, int outputTokens) {
        var pricing = models.get(model);
        double inputRate = pricing != null ? pricing.input() : FALLBACK_INPUT;
        double outputRate = pricing != null ? pricing.output() : FALLBACK_OUTPUT;
        return (inputTokens * inputRate + outputTokens * outputRate) / PER_MILLION;
    }

    public boolean hasModel(String model) {
        return models.containsKey(model);
    }
}
