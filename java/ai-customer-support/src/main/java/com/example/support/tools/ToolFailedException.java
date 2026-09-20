package com.example.support.tools;

/** A tool that completed but could not do what it was asked. */
public class ToolFailedException extends RuntimeException {

    public ToolFailedException(String message) {
        super(message);
    }
}
