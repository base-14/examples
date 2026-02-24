package middleware

import (
	"fmt"
	"net/http"

	"github.com/go-chi/chi/v5"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

func OTelHTTP(serviceName string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return otelhttp.NewMiddleware(serviceName,
			otelhttp.WithSpanNameFormatter(func(_ string, r *http.Request) string {
				routePattern := chi.RouteContext(r.Context()).RoutePattern()
				if routePattern == "" {
					routePattern = r.URL.Path
				}
				return fmt.Sprintf("%s %s", r.Method, routePattern)
			}),
			otelhttp.WithFilter(func(r *http.Request) bool {
				return r.URL.Path != "/api/health"
			}),
		)(next)
	}
}
