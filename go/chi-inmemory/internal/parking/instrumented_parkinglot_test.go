package parking

import (
	"context"
	"testing"
)

func TestInstrumentedParkingLotIntegration(t *testing.T) {
	// Initialize telemetry
	telemetry, err := NewTelemetryProvider()
	if err != nil {
		t.Fatalf("Failed to initialize telemetry: %v", err)
	}
	defer func() {
		if err := telemetry.Shutdown(context.Background()); err != nil {
			t.Errorf("Failed to shutdown telemetry: %v", err)
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
