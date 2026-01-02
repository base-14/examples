package com.base14.demo.service;

public class ServiceException extends RuntimeException {

    private final int statusCode;

    public ServiceException(String message, int statusCode) {
        super(message);
        this.statusCode = statusCode;
    }

    public int getStatusCode() {
        return statusCode;
    }
}
