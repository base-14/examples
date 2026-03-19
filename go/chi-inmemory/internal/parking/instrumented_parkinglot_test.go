package parking

import (
	"context"
	"os"
	"testing"
)

func TestInstrumentedParkingLotIntegration(t *testing.T) {
	// Point exporter at a non-existent but valid endpoint so the test
	// doesn't depend on a running collector. The SDK batches async, so
	// export errors don't surface during the test itself.
	if os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT") == "" {
		t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
	}

	// Initialize telemetry
	telemetry, err := NewTelemetryProvider()
	if err != nil {
		t.Fatalf("Failed to initialize telemetry: %v", err)
	}
	defer func() {
		if err := telemetry.Shutdown(context.Background()); err != nil {
			t.Logf("Telemetry shutdown (expected when no collector): %v", err)
		}
	}()

	// Create instrumented parking lot
	ipl, err := NewInstrumentedParkingLot(3, telemetry)
	if err != nil {
		t.Fatalf("Failed to create instrumented parking lot: %v", err)
	}

	ctx := context.Background()

	// Test parking operations
	slotNumber, err := ipl.Park(ctx, "KA01HH1234", "White")
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}
	if slotNumber != 1 {
		t.Errorf("Expected slot number 1, got %d", slotNumber)
	}

	// Test status
	status := ipl.GetStatus(ctx)
	if len(status) != 1 {
		t.Errorf("Expected 1 occupied slot, got %d", len(status))
	}

	// Test slot lookup
	foundSlot, err := ipl.GetSlotByRegistrationNumber(ctx, "KA01HH1234")
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}
	if foundSlot != 1 {
		t.Errorf("Expected slot number 1, got %d", foundSlot)
	}

	// Test leaving
	err = ipl.Leave(ctx, 1)
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}

	// Verify slot is free
	status = ipl.GetStatus(ctx)
	if len(status) != 0 {
		t.Errorf("Expected 0 occupied slots, got %d", len(status))
	}
}
