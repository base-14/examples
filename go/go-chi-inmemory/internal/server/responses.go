package server

import (
	"context"
	"encoding/json"
	"net/http"

	"go.opentelemetry.io/otel/trace"
)

type Meta struct {
	TraceID   string `json:"trace_id,omitempty"`
	RequestID string `json:"request_id,omitempty"`
}

type Response struct {
	Success bool   `json:"success"`
	Message string `json:"message,omitempty"`
	Data    any    `json:"data,omitempty"`
	Error   string `json:"error,omitempty"`
	Meta    *Meta  `json:"meta,omitempty"`
}

type HealthResponse struct {
	Status  string `json:"status"`
	Service string `json:"service"`
}

type ParkingLotCreateRequest struct {
	Capacity int `json:"capacity"`
}

type ParkVehicleRequest struct {
	Registration string `json:"registration"`
	Color        string `json:"color"`
}

type LeaveSlotRequest struct {
	SlotNumber int `json:"slot_number"`
}

type FindVehicleResponse struct {
	SlotNumber   int    `json:"slot_number"`
	Registration string `json:"registration"`
	Color        string `json:"color"`
}

type SlotStatus struct {
	SlotNumber   int    `json:"slot_number"`
	Registration string `json:"registration,omitempty"`
	Color        string `json:"color,omitempty"`
	Occupied     bool   `json:"occupied"`
}

type StatusResponse struct {
	Capacity  int          `json:"capacity"`
	Occupied  int          `json:"occupied"`
	Available int          `json:"available"`
	Slots     []SlotStatus `json:"slots"`
}

func WriteJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func extractMeta(ctx context.Context) *Meta {
	meta := &Meta{}

	span := trace.SpanFromContext(ctx)
	if span.SpanContext().HasTraceID() {
		meta.TraceID = span.SpanContext().TraceID().String()
	}

	if reqID, ok := ctx.Value(RequestIDKey).(string); ok {
		meta.RequestID = reqID
	}

	return meta
}

func WriteSuccess(ctx context.Context, w http.ResponseWriter, message string, data any) {
	WriteJSON(w, http.StatusOK, Response{
		Success: true,
		Message: message,
		Data:    data,
		Meta:    extractMeta(ctx),
	})
}

func WriteError(ctx context.Context, w http.ResponseWriter, status int, message string) {
	WriteJSON(w, status, Response{
		Success: false,
		Error:   message,
		Meta:    extractMeta(ctx),
	})
}
