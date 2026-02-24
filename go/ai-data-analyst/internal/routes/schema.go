package routes

import (
	"net/http"
	"os"
	"path/filepath"
	"runtime"
)

func SchemaHandler() http.HandlerFunc {
	content := loadSchemaContext()
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.Write([]byte(content))
	}
}

func loadSchemaContext() string {
	paths := []string{
		"/app/data/schema-context.txt",
	}
	if _, filename, _, ok := runtime.Caller(0); ok {
		dir := filepath.Dir(filename)
		paths = append(paths, filepath.Join(dir, "..", "..", "data", "schema-context.txt"))
	}
	for _, p := range paths {
		data, err := os.ReadFile(p)
		if err == nil {
			return string(data)
		}
	}
	return "Schema context not available"
}
