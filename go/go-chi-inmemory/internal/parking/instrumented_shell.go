package parking

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

type InstrumentedShell struct {
	instrumentedParkingLot *InstrumentedParkingLot
	scanner                *bufio.Scanner
	telemetry              *TelemetryProvider
}

func NewInstrumentedShell(telemetry *TelemetryProvider) *InstrumentedShell {
	return &InstrumentedShell{
		scanner:   bufio.NewScanner(os.Stdin),
		telemetry: telemetry,
	}
}

func (s *InstrumentedShell) Run(ctx context.Context) {
	tracer := s.telemetry.Tracer()
	ctx, span := tracer.Start(ctx, "shell.run")
	defer span.End()

	span.AddEvent("shell_started")

	for {
		if !s.scanner.Scan() {
			break
		}

		input := strings.TrimSpace(s.scanner.Text())
		if input == "" {
			continue
		}

		// Create a new span for each command
		cmdCtx, cmdSpan := tracer.Start(ctx, "shell.process_command",
			trace.WithAttributes(attribute.String("command.input", input)))

		s.processCommand(cmdCtx, input)
		cmdSpan.End()
	}

	span.AddEvent("shell_ended")
}

func (s *InstrumentedShell) processCommand(ctx context.Context, input string) {
	tracer := s.telemetry.Tracer()
	_, span := tracer.Start(ctx, "shell.parse_command")
	defer span.End()

	parts := strings.Fields(input)
	if len(parts) == 0 {
		return
	}

	command := parts[0]
	span.SetAttributes(attribute.String("command.name", command))

	switch command {
	case "create_parking_lot":
		s.handleCreateParkingLot(ctx, parts)
	case "park":
		s.handlePark(ctx, parts)
	case "leave":
		s.handleLeave(ctx, parts)
	case "status":
		s.handleStatus(ctx)
	case "slot_number_for_registration_number":
		s.handleSlotNumberForRegistrationNumber(ctx, parts)
	default:
		span.AddEvent("unknown_command", trace.WithAttributes(
			attribute.String("unknown_command", command),
		))
		fmt.Printf("Unknown command: %s\n", command)
	}
}

func (s *InstrumentedShell) handleCreateParkingLot(ctx context.Context, parts []string) {
	tracer := s.telemetry.Tracer()
	_, span := tracer.Start(ctx, "shell.create_parking_lot")
	defer span.End()

	if len(parts) != 2 {
		span.AddEvent("invalid_arguments")
		fmt.Println("Usage: create_parking_lot <capacity>")
		return
	}

	capacity, err := strconv.Atoi(parts[1])
	if err != nil || capacity <= 0 {
		span.RecordError(fmt.Errorf("invalid capacity: %s", parts[1]))
		span.AddEvent("invalid_capacity")
		fmt.Println("Invalid capacity")
		return
	}

	span.SetAttributes(attribute.Int("parking_lot.capacity", capacity))

	instrumentedParkingLot, err := NewInstrumentedParkingLot(capacity, s.telemetry)
	if err != nil {
		span.RecordError(err)
		fmt.Printf("Error creating parking lot: %s\n", err.Error())
		return
	}

	s.instrumentedParkingLot = instrumentedParkingLot
	span.AddEvent("parking_lot_created")
	fmt.Printf("Created a parking lot with %d slots\n", capacity)
}

func (s *InstrumentedShell) handlePark(ctx context.Context, parts []string) {
	tracer := s.telemetry.Tracer()
	_, span := tracer.Start(ctx, "shell.park_command")
	defer span.End()

	if s.instrumentedParkingLot == nil {
		span.AddEvent("parking_lot_not_created")
		fmt.Println("Parking lot not created")
		return
	}

	if len(parts) != 3 {
		span.AddEvent("invalid_arguments")
		fmt.Println("Usage: park <registration_number> <color>")
		return
	}

	registrationNumber := parts[1]
	color := parts[2]

	span.SetAttributes(
		attribute.String("vehicle.registration_number", registrationNumber),
		attribute.String("vehicle.color", color),
	)

	slotNumber, err := s.instrumentedParkingLot.Park(ctx, registrationNumber, color)
	if err != nil {
		span.AddEvent("parking_failed")
		fmt.Println("Sorry, parking lot is full")
		return
	}

	span.AddEvent("parking_successful", trace.WithAttributes(
		attribute.Int("allocated_slot", slotNumber),
	))
	fmt.Printf("Allocated slot number: %d\n", slotNumber)
}

func (s *InstrumentedShell) handleLeave(ctx context.Context, parts []string) {
	tracer := s.telemetry.Tracer()
	_, span := tracer.Start(ctx, "shell.leave_command")
	defer span.End()

	if s.instrumentedParkingLot == nil {
		span.AddEvent("parking_lot_not_created")
		fmt.Println("Parking lot not created")
		return
	}

	if len(parts) != 2 {
		span.AddEvent("invalid_arguments")
		fmt.Println("Usage: leave <slot_number>")
		return
	}

	slotNumber, err := strconv.Atoi(parts[1])
	if err != nil {
		span.RecordError(fmt.Errorf("invalid slot number: %s", parts[1]))
		span.AddEvent("invalid_slot_number")
		fmt.Println("Invalid slot number")
		return
	}

	span.SetAttributes(attribute.Int("slot_number", slotNumber))

	err = s.instrumentedParkingLot.Leave(ctx, slotNumber)
	if err != nil {
		span.AddEvent("leave_failed")
		fmt.Printf("Error: %s\n", err.Error())
		return
	}

	span.AddEvent("leave_successful")
	fmt.Printf("Slot number %d is free\n", slotNumber)
}

func (s *InstrumentedShell) handleStatus(ctx context.Context) {
	tracer := s.telemetry.Tracer()
	_, span := tracer.Start(ctx, "shell.status_command")
	defer span.End()

	if s.instrumentedParkingLot == nil {
		span.AddEvent("parking_lot_not_created")
		fmt.Println("Parking lot not created")
		return
	}

	occupiedSlots := s.instrumentedParkingLot.GetStatus(ctx)
	if len(occupiedSlots) == 0 {
		span.AddEvent("parking_lot_empty")
		fmt.Println("Parking lot is empty")
		return
	}

	span.SetAttributes(attribute.Int("occupied_slots_count", len(occupiedSlots)))
	span.AddEvent("status_retrieved")

	fmt.Println("Slot No.\tRegistration No\tColour")
	for _, slot := range occupiedSlots {
		fmt.Printf("%d\t\t%s\t%s\n", slot.Number, slot.Vehicle.RegistrationNumber, slot.Vehicle.Color)
	}
}

func (s *InstrumentedShell) handleSlotNumberForRegistrationNumber(ctx context.Context, parts []string) {
	tracer := s.telemetry.Tracer()
	_, span := tracer.Start(ctx, "shell.find_slot_by_registration")
	defer span.End()

	if s.instrumentedParkingLot == nil {
		span.AddEvent("parking_lot_not_created")
		fmt.Println("Parking lot not created")
		return
	}

	if len(parts) != 2 {
		span.AddEvent("invalid_arguments")
		fmt.Println("Usage: slot_number_for_registration_number <registration_number>")
		return
	}

	registrationNumber := parts[1]
	span.SetAttributes(attribute.String("registration_number", registrationNumber))

	slotNumber, err := s.instrumentedParkingLot.GetSlotByRegistrationNumber(ctx, registrationNumber)
	if err != nil {
		span.AddEvent("vehicle_not_found")
		fmt.Println("Not found")
		return
	}

	span.AddEvent("vehicle_found", trace.WithAttributes(
		attribute.Int("slot_number", slotNumber),
	))
	fmt.Printf("%d\n", slotNumber)
}
