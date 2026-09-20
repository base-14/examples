package com.example.support.telemetry;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Loads a contract vector from {@code _shared/test-vectors}, copied onto the test classpath. */
public final class TestVectors {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private TestVectors() {
    }

    public static JsonNode load(String name) {
        try (InputStream stream = TestVectors.class.getClassLoader()
            .getResourceAsStream("test-vectors/" + name)) {
            if (stream == null) {
                throw new IllegalStateException("Vector not on the test classpath: " + name);
            }
            return MAPPER.readTree(stream);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
