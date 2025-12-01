package main

import (
	"context"
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"parking-lot/internal/parking"
	"parking-lot/internal/server"
)

var (
	mode = flag.String("mode", "cli", "Mode to run: cli, server, or both")
	port = flag.String("port", "8080", "Port for HTTP server")
)

func main() {
	flag.Parse()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	telemetryProvider, err := parking.NewTelemetryProvider()
	if err != nil {
		log.Fatalf("Failed to initialize telemetry: %v", err)
	}

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	switch *mode {
	case "cli":
		runCLI(ctx, cancel, telemetryProvider, sigChan)
	case "server":
		runServer(ctx, cancel, telemetryProvider, sigChan)
	case "both":
		runBoth(ctx, cancel, telemetryProvider, sigChan)
	default:
		log.Fatalf("Invalid mode: %s. Must be cli, server, or both", *mode)
	}
}

func runCLI(ctx context.Context, cancel context.CancelFunc, telemetryProvider *parking.TelemetryProvider, sigChan chan os.Signal) {
	go func() {
		<-sigChan
		log.Println("Shutting down...")
		cancel()
	}()

	shell := parking.NewInstrumentedShell(telemetryProvider)
	shell.Run(ctx)

	shutdownTelemetry(telemetryProvider)
}

func runServer(ctx context.Context, cancel context.CancelFunc, telemetryProvider *parking.TelemetryProvider, sigChan chan os.Signal) {
	srv := server.NewServer(*port)

	go func() {
		<-sigChan
		log.Println("Received shutdown signal...")

		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()

		if err := srv.Shutdown(shutdownCtx); err != nil {
			log.Printf("Server shutdown error: %v", err)
		}

		cancel()
	}()

	log.Printf("Starting server mode on port %s", *port)
	if err := srv.Start(); err != nil && err != context.Canceled {
		log.Printf("Server error: %v", err)
	}

	shutdownTelemetry(telemetryProvider)
}

func runBoth(ctx context.Context, cancel context.CancelFunc, telemetryProvider *parking.TelemetryProvider, sigChan chan os.Signal) {
	srv := server.NewServer(*port)

	serverDone := make(chan error, 1)
	go func() {
		log.Printf("Starting HTTP server on port %s", *port)
		serverDone <- srv.Start()
	}()

	cliDone := make(chan bool, 1)
	go func() {
		shell := parking.NewInstrumentedShell(telemetryProvider)
		shell.Run(ctx)
		cliDone <- true
	}()

	go func() {
		<-sigChan
		log.Println("Received shutdown signal...")

		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()

		if err := srv.Shutdown(shutdownCtx); err != nil {
			log.Printf("Server shutdown error: %v", err)
		}

		cancel()
	}()

	select {
	case err := <-serverDone:
		if err != nil && err != context.Canceled {
			log.Printf("Server error: %v", err)
		}
	case <-cliDone:
		log.Println("CLI exited")
	case <-ctx.Done():
		log.Println("Context cancelled")
	}

	shutdownTelemetry(telemetryProvider)
}

func shutdownTelemetry(telemetryProvider *parking.TelemetryProvider) {
	log.Println("Shutting down telemetry...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()

	if err := telemetryProvider.Shutdown(shutdownCtx); err != nil {
		log.Printf("Error shutting down telemetry: %v", err)
	}
}
