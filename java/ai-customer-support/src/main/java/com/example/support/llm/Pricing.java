package com.example.support.llm;

import java.io.IOException;
import java.io.InputStream;
import java.util.Map;
import java.util.regex.Pattern;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Per-million-token rates from {@code _shared/pricing.json}, which the build copies
 * onto the classpath. A model the file does not list costs 0.0.
 */
@Component
public class Pricing {

    private static final Logger log = LoggerFactory.getLogger(Pricing.class);
    private static final double PER_MILLION = 1_000_000.0;
    private static final Pattern DATE_SUFFIX = Pattern.compile("-\\d{4}-\\d{2}-\\d{2}$|-\\d{8}$");
    private static final Pattern DASH_MINOR = Pattern.compile("-(\\d+)-(\\d+)$");

    private final Map<String, ModelPricing> models;

    @JsonIgnoreProperties(ignoreUnknown = true)
    record PricingFile(String version, Map<String, ModelPricing> models) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ModelPricing(String provider, double input, double output) {}

    public Pricing() {
        this.models = load();
    }

    private static Map<String, ModelPricing> load() {
        try (InputStream stream = Pricing.class.getClassLoader().getResourceAsStream("pricing.json")) {
            if (stream == null) {
                log.warn("pricing.json not on the classpath, every model costs 0.0");
                return Map.of();
            }
            PricingFile file = new ObjectMapper().readValue(stream, PricingFile.class);
            log.info("Loaded pricing {} with {} models", file.version(), file.models().size());
            return file.models();
        } catch (IOException e) {
            log.warn("Failed to read pricing.json: {}", e.getMessage());
            return Map.of();
        }
    }

    /**
     * Maps a dated or dash-minor model id ("claude-sonnet-4-20250514",
     * "claude-haiku-4-5") to the dot key pricing.json uses.
     */
    static String normalizeModel(String model) {
        String stripped = DATE_SUFFIX.matcher(model).replaceAll("");
        return DASH_MINOR.matcher(stripped).replaceAll("-$1.$2");
    }

    public double calculateCost(String model, int inputTokens, int outputTokens) {
        ModelPricing pricing = models.get(model);
        if (pricing == null) {
            pricing = models.get(normalizeModel(model));
        }
        if (pricing == null) {
            return 0.0;
        }
        return (inputTokens * pricing.input() + outputTokens * pricing.output()) / PER_MILLION;
    }

    public boolean hasModel(String model) {
        return models.containsKey(model) || models.containsKey(normalizeModel(model));
    }
}
