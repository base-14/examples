package server

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

type Server struct {
	httpServer *http.Server
	handler    *Handler
}

func NewServer(port string) *Server {
	handler := NewHandler()

	r := chi.NewRouter()

	r.Use(RecoveryMiddleware)
	r.Use(RequestIDMiddleware)
	r.Use(LoggingMiddleware)
	r.Use(TracingMiddleware)
	r.Use(CORSMiddleware)

	r.Get("/health", handler.HealthCheck)
	r.Get("/metrics", promhttp.Handler().ServeHTTP)

	r.Route("/api/parking-lot", func(r chi.Router) {
		r.Post("/", handler.CreateParkingLot)
		r.Post("/park", handler.ParkVehicle)
		r.Post("/leave", handler.LeaveSlot)
		r.Get("/status", handler.GetStatus)
		r.Get("/find/{registration}", handler.FindByRegistration)
	})

	httpServer := &http.Server{
		Addr:         ":" + port,
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	return &Server{
		httpServer: httpServer,
		handler:    handler,
	}
}

func (s *Server) Start() error {
	log.Printf("Starting HTTP server on %s", s.httpServer.Addr)
	return s.httpServer.ListenAndServe()
}

func (s *Server) Shutdown(ctx context.Context) error {
	log.Println("Shutting down HTTP server...")
	return s.httpServer.Shutdown(ctx)
}

func (s *Server) GetAddress() string {
	return fmt.Sprintf("http://localhost%s", s.httpServer.Addr)
}
