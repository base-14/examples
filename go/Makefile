.PHONY: build test clean run

BINARY_NAME=my_program
MAIN_PACKAGE=./cmd/parking-lot

build:
	go build -o $(BINARY_NAME) $(MAIN_PACKAGE)

test:
	go test ./...

clean:
	go clean
	rm -f $(BINARY_NAME)

run: build
	./$(BINARY_NAME)

.DEFAULT_GOAL := build