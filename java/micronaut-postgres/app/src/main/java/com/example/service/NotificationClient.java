package com.example.service;

import io.micronaut.context.annotation.Value;
import io.micronaut.json.JsonMapper;
import jakarta.inject.Singleton;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

@Singleton
public class NotificationClient {

    private static final Logger LOG = LoggerFactory.getLogger(NotificationClient.class);

    private final HttpClient httpClient = HttpClient.newHttpClient();
    private final JsonMapper jsonMapper;
    private final String notifyUrl;

    public NotificationClient(@Value("${notify.url:`http://localhost:8081`}") String notifyUrl, JsonMapper jsonMapper) {
        this.notifyUrl = notifyUrl;
        this.jsonMapper = jsonMapper;
    }

    public void notify(Map<String, Object> payload) {
        try {
            String json = jsonMapper.writeValueAsString(payload);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(notifyUrl + "/notify"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            LOG.debug("Notify response: {}", response.statusCode());
        } catch (Exception e) {
            LOG.warn("Failed to notify: {}", e.getMessage());
        }
    }
}
