package com.example.support.controller;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;

import com.example.support.telemetry.GenAi;

/** Turns uncaught errors into responses and records them on the active span. */
@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> handleResponseStatus(ResponseStatusException e) {
        HttpStatus status = HttpStatus.valueOf(e.getStatusCode().value());
        if (status.isError()) {
            record(e, status.value());
        }
        return ResponseEntity.status(status).body(Map.of("error", e.getReason() != null ? e.getReason() : status.getReasonPhrase()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(IllegalArgumentException e) {
        record(e, HttpStatus.BAD_REQUEST.value());
        return ResponseEntity.badRequest().body(Map.of("error", String.valueOf(e.getMessage())));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleUnexpected(Exception e) {
        record(e, HttpStatus.INTERNAL_SERVER_ERROR.value());
        log.error("Unhandled request failure", e);
        return ResponseEntity.internalServerError().body(Map.of("error", "Internal server error"));
    }

    private static void record(Exception e, int statusCode) {
        Span span = Span.current();
        span.recordException(e);
        span.setAttribute(GenAi.ERROR_TYPE, e.getClass().getSimpleName());
        span.setAttribute("http.response.status_code", statusCode);
        span.setStatus(StatusCode.ERROR, String.valueOf(e.getMessage()));
    }
}
