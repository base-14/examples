package com.example.notify.controller;

import io.micronaut.http.HttpResponse;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.Post;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.util.Map;

@Controller
public class NotifyController {

    private static final Logger LOG = LoggerFactory.getLogger(NotifyController.class);

    @Post("/notify")
    public Map<String, Object> notify(@Body Map<String, Object> payload) {
        LOG.info("Notification received: article_id={}, title={}",
                payload.get("id"), payload.get("title"));
        return Map.of("data", Map.of("status", "notified"));
    }

    @Get("/health")
    public HttpResponse<Map<String, Object>> health() {
        return HttpResponse.ok(Map.of("data", Map.of("status", "ok")));
    }
}
