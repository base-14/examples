package server

import (
	"encoding/json"
	"net/http"
	"os"
	"parking-lot/internal/parking"
	"sync"

	"github.com/go-chi/chi/v5"
)

func getServiceName() string {
	if name := os.Getenv("OTEL_SERVICE_NAME"); name != "" {
		return name
	}
	return "go-parking-lot-otel"
}

type Handler struct {
	parkingLot *parking.InstrumentedParkingLot
	mu         sync.RWMutex
}

func NewHandler() *Handler {
	return &Handler{}
}

func (h *Handler) HealthCheck(w http.ResponseWriter, r *http.Request) {
	WriteJSON(w, http.StatusOK, map[string]any{
		"status":  "healthy",
		"service": getServiceName(),
		"meta":    extractMeta(r.Context()),
	})
}

func (h *Handler) CreateParkingLot(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req ParkingLotCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(ctx, w, http.StatusBadRequest, "Invalid request body")
		return
	}

	if req.Capacity <= 0 {
		WriteError(ctx, w, http.StatusBadRequest, "Capacity must be greater than 0")
		return
	}

	h.mu.Lock()
	defer h.mu.Unlock()

	telemetry, err := parking.NewTelemetryProvider()
	if err != nil {
		WriteError(ctx, w, http.StatusInternalServerError, "Failed to initialize telemetry")
		return
	}

	parkingLot, err := parking.NewInstrumentedParkingLot(req.Capacity, telemetry)
	if err != nil {
		WriteError(ctx, w, http.StatusInternalServerError, "Failed to create parking lot")
		return
	}

	h.parkingLot = parkingLot

	WriteSuccess(ctx, w, "Parking lot created successfully", map[string]any{
		"capacity": req.Capacity,
	})
}

func (h *Handler) ParkVehicle(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	h.mu.RLock()
	if h.parkingLot == nil {
		h.mu.RUnlock()
		WriteError(ctx, w, http.StatusBadRequest, "Parking lot not created. Create parking lot first")
		return
	}
	h.mu.RUnlock()

	var req ParkVehicleRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(ctx, w, http.StatusBadRequest, "Invalid request body")
		return
	}

	if req.Registration == "" || req.Color == "" {
		WriteError(ctx, w, http.StatusBadRequest, "Registration and color are required")
		return
	}

	slotNumber, err := h.parkingLot.Park(ctx, req.Registration, req.Color)
	if err != nil {
		WriteError(ctx, w, http.StatusConflict, err.Error())
		return
	}

	WriteSuccess(ctx, w, "Vehicle parked successfully", map[string]any{
		"slot_number":  slotNumber,
		"registration": req.Registration,
		"color":        req.Color,
	})
}

func (h *Handler) LeaveSlot(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	h.mu.RLock()
	if h.parkingLot == nil {
		h.mu.RUnlock()
		WriteError(ctx, w, http.StatusBadRequest, "Parking lot not created. Create parking lot first")
		return
	}
	h.mu.RUnlock()

	var req LeaveSlotRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(ctx, w, http.StatusBadRequest, "Invalid request body")
		return
	}

	if req.SlotNumber <= 0 {
		WriteError(ctx, w, http.StatusBadRequest, "Slot number must be greater than 0")
		return
	}

	err := h.parkingLot.Leave(ctx, req.SlotNumber)
	if err != nil {
		WriteError(ctx, w, http.StatusBadRequest, err.Error())
		return
	}

	WriteSuccess(ctx, w, "Slot vacated successfully", map[string]any{
		"slot_number": req.SlotNumber,
	})
}

func (h *Handler) GetStatus(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	h.mu.RLock()
	if h.parkingLot == nil {
		h.mu.RUnlock()
		WriteError(ctx, w, http.StatusBadRequest, "Parking lot not created. Create parking lot first")
		return
	}
	h.mu.RUnlock()

	occupiedSlots := h.parkingLot.GetStatus(ctx)

	var slots []SlotStatus
	capacity := h.parkingLot.ParkingLot.GetCapacity()

	for i := 1; i <= capacity; i++ {
		slot := SlotStatus{
			SlotNumber: i,
			Occupied:   false,
		}

		for _, occupiedSlot := range occupiedSlots {
			if occupiedSlot.Number == i {
				slot.Occupied = true
				slot.Registration = occupiedSlot.Vehicle.RegistrationNumber
				slot.Color = occupiedSlot.Vehicle.Color
				break
			}
		}

		slots = append(slots, slot)
	}

	response := StatusResponse{
		Capacity:  capacity,
		Occupied:  len(occupiedSlots),
		Available: capacity - len(occupiedSlots),
		Slots:     slots,
	}

	WriteSuccess(ctx, w, "Status retrieved successfully", response)
}

func (h *Handler) FindByRegistration(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	h.mu.RLock()
	if h.parkingLot == nil {
		h.mu.RUnlock()
		WriteError(ctx, w, http.StatusBadRequest, "Parking lot not created. Create parking lot first")
		return
	}
	h.mu.RUnlock()

	registration := chi.URLParam(r, "registration")
	if registration == "" {
		WriteError(ctx, w, http.StatusBadRequest, "Registration number is required")
		return
	}

	slotNumber, err := h.parkingLot.GetSlotByRegistrationNumber(ctx, registration)
	if err != nil {
		WriteError(ctx, w, http.StatusNotFound, "Vehicle not found")
		return
	}

	occupiedSlots := h.parkingLot.GetStatus(ctx)
	var vehicleInfo *parking.Vehicle

	for _, slot := range occupiedSlots {
		if slot.Number == slotNumber {
			vehicleInfo = slot.Vehicle
			break
		}
	}

	if vehicleInfo == nil {
		WriteError(ctx, w, http.StatusNotFound, "Vehicle not found")
		return
	}

	response := FindVehicleResponse{
		SlotNumber:   slotNumber,
		Registration: vehicleInfo.RegistrationNumber,
		Color:        vehicleInfo.Color,
	}

	WriteSuccess(ctx, w, "Vehicle found", response)
}
