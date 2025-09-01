package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"parking-lot/internal/parking"
)

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Initialize telemetry
	telemetryProvider, err := parking.NewTelemetryProvider()
	if err != nil {
		log.Fatalf("Failed to initialize telemetry: %v", err)
	}

	// Graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan
		
		log.Println("Shutting down telemetry...")
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		
		if err := telemetryProvider.Shutdown(shutdownCtx); err != nil {
			log.Printf("Error shutting down telemetry: %v", err)
		}
		
		cancel()
		os.Exit(0)
	}()

	// Create and run instrumented shell
	shell := parking.NewInstrumentedShell(telemetryProvider)
	shell.Run(ctx)

	// Shutdown telemetry when shell exits
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	
	if err := telemetryProvider.Shutdown(shutdownCtx); err != nil {
		log.Printf("Error shutting down telemetry: %v", err)
	}
}