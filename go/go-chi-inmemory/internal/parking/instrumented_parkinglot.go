package parking

import (
	"context"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"
)

type InstrumentedParkingLot struct {
	*ParkingLot
	telemetry *TelemetryProvider

	// Metrics
	parkingOperations metric.Int64Counter
	leavingOperations metric.Int64Counter
	occupancyGauge    metric.Int64UpDownCounter
	operationDuration metric.Float64Histogram
	totalSlotsGauge   metric.Int64UpDownCounter
}

func NewInstrumentedParkingLot(capacity int, telemetry *TelemetryProvider) (*InstrumentedParkingLot, error) {
	baseParkingLot := NewParkingLot(capacity)

	meter := telemetry.Meter()

	parkingOperations, err := meter.Int64Counter("parking_operations_total",
		metric.WithDescription("Total number of parking operations"),
		metric.WithUnit("1"))
	if err != nil {
		return nil, err
	}

	leavingOperations, err := meter.Int64Counter("leaving_operations_total",
		metric.WithDescription("Total number of leaving operations"),
		metric.WithUnit("1"))
	if err != nil {
		return nil, err
	}

	occupancyGauge, err := meter.Int64UpDownCounter("parking_lot_occupancy",
		metric.WithDescription("Current number of occupied parking slots"),
		metric.WithUnit("1"))
	if err != nil {
		return nil, err
	}

	operationDuration, err := meter.Float64Histogram("operation_duration_seconds",
		metric.WithDescription("Duration of parking lot operations"),
		metric.WithUnit("s"))
	if err != nil {
		return nil, err
	}

	totalSlotsGauge, err := meter.Int64UpDownCounter("parking_lot_total_slots",
		metric.WithDescription("Total number of parking slots"),
		metric.WithUnit("1"))
	if err != nil {
		return nil, err
	}

	ipl := &InstrumentedParkingLot{
		ParkingLot:        baseParkingLot,
		telemetry:         telemetry,
		parkingOperations: parkingOperations,
		leavingOperations: leavingOperations,
		occupancyGauge:    occupancyGauge,
		operationDuration: operationDuration,
		totalSlotsGauge:   totalSlotsGauge,
	}

	// Set initial total slots metric
	totalSlotsGauge.Add(context.Background(), int64(capacity))

	return ipl, nil
}

func (ipl *InstrumentedParkingLot) Park(ctx context.Context, registrationNumber, color string) (int, error) {
	tracer := ipl.telemetry.Tracer()
	ctx, span := tracer.Start(ctx, "parking_lot.park",
		trace.WithAttributes(
			attribute.String("vehicle.registration_number", registrationNumber),
			attribute.String("vehicle.color", color),
		))
	defer span.End()

	start := time.Now()

	span.AddEvent("finding_available_slot")

	slotNumber, err := ipl.ParkingLot.Park(registrationNumber, color)

	duration := time.Since(start).Seconds()

	labels := []attribute.KeyValue{
		attribute.String("operation", "park"),
		attribute.String("vehicle_color", color),
	}

	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		labels = append(labels, attribute.String("status", "failed"))
		ipl.parkingOperations.Add(ctx, 1, metric.WithAttributes(labels...))
	} else {
		labels = append(labels,
			attribute.String("status", "success"),
			attribute.Int("allocated_slot", slotNumber),
		)
		span.SetAttributes(attribute.Int("allocated_slot_number", slotNumber))
		span.AddEvent("slot_allocated", trace.WithAttributes(
			attribute.Int("slot_number", slotNumber),
		))

		ipl.parkingOperations.Add(ctx, 1, metric.WithAttributes(labels...))
		ipl.occupancyGauge.Add(ctx, 1)
	}

	ipl.operationDuration.Record(ctx, duration, metric.WithAttributes(labels...))

	return slotNumber, err
}

func (ipl *InstrumentedParkingLot) Leave(ctx context.Context, slotNumber int) error {
	tracer := ipl.telemetry.Tracer()
	ctx, span := tracer.Start(ctx, "parking_lot.leave",
		trace.WithAttributes(
			attribute.Int("slot_number", slotNumber),
		))
	defer span.End()

	start := time.Now()

	// Get vehicle info before leaving for metrics
	var vehicleInfo *Vehicle
	if slotNumber >= 1 && slotNumber <= ipl.capacity {
		slot := ipl.slots[slotNumber-1]
		if slot.IsOccupied {
			vehicleInfo = slot.Vehicle
		}
	}

	span.AddEvent("releasing_slot")

	err := ipl.ParkingLot.Leave(slotNumber)

	duration := time.Since(start).Seconds()

	labels := []attribute.KeyValue{
		attribute.String("operation", "leave"),
		attribute.Int("slot_number", slotNumber),
	}

	if vehicleInfo != nil {
		labels = append(labels,
			attribute.String("vehicle_registration", vehicleInfo.RegistrationNumber),
			attribute.String("vehicle_color", vehicleInfo.Color),
		)
		span.SetAttributes(
			attribute.String("vehicle.registration_number", vehicleInfo.RegistrationNumber),
			attribute.String("vehicle.color", vehicleInfo.Color),
		)
	}

	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		labels = append(labels, attribute.String("status", "failed"))
	} else {
		labels = append(labels, attribute.String("status", "success"))
		span.AddEvent("slot_released")
		ipl.occupancyGauge.Add(ctx, -1)
	}

	ipl.leavingOperations.Add(ctx, 1, metric.WithAttributes(labels...))
	ipl.operationDuration.Record(ctx, duration, metric.WithAttributes(labels...))

	return err
}

func (ipl *InstrumentedParkingLot) GetStatus(ctx context.Context) []*Slot {
	tracer := ipl.telemetry.Tracer()
	ctx, span := tracer.Start(ctx, "parking_lot.get_status")
	defer span.End()

	start := time.Now()

	span.AddEvent("retrieving_status")

	occupiedSlots := ipl.ParkingLot.GetStatus()

	duration := time.Since(start).Seconds()

	span.SetAttributes(
		attribute.Int("occupied_slots_count", len(occupiedSlots)),
		attribute.Int("total_capacity", ipl.capacity),
	)

	labels := []attribute.KeyValue{
		attribute.String("operation", "get_status"),
		attribute.String("status", "success"),
	}

	ipl.operationDuration.Record(ctx, duration, metric.WithAttributes(labels...))

	return occupiedSlots
}

func (ipl *InstrumentedParkingLot) GetSlotByRegistrationNumber(ctx context.Context, registrationNumber string) (int, error) {
	tracer := ipl.telemetry.Tracer()
	ctx, span := tracer.Start(ctx, "parking_lot.get_slot_by_registration",
		trace.WithAttributes(
			attribute.String("registration_number", registrationNumber),
		))
	defer span.End()

	start := time.Now()

	span.AddEvent("searching_by_registration")

	slotNumber, err := ipl.ParkingLot.GetSlotByRegistrationNumber(registrationNumber)

	duration := time.Since(start).Seconds()

	labels := []attribute.KeyValue{
		attribute.String("operation", "get_slot_by_registration"),
		attribute.String("registration_number", registrationNumber),
	}

	if err != nil {
		span.AddEvent("vehicle_not_found")
		labels = append(labels, attribute.String("status", "not_found"))
	} else {
		span.SetAttributes(attribute.Int("found_slot_number", slotNumber))
		span.AddEvent("vehicle_found", trace.WithAttributes(
			attribute.Int("slot_number", slotNumber),
		))
		labels = append(labels,
			attribute.String("status", "found"),
			attribute.Int("slot_number", slotNumber),
		)
	}

	ipl.operationDuration.Record(ctx, duration, metric.WithAttributes(labels...))

	return slotNumber, err
}
