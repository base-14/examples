# Parking Lot Management System

A Go-based parking lot management system with an interactive command-line interface.

## Project Structure

```
parking-lot/
├── cmd/parking-lot/          # Main application entry point
│   └── main.go
├── internal/parking/         # Core business logic
│   ├── parkinglot.go        # Parking lot implementation
│   ├── vehicle.go           # Vehicle data structure
│   ├── slot.go              # Parking slot implementation
│   ├── shell.go             # Interactive shell interface
│   └── *_test.go            # Unit tests
├── Makefile                 # Build automation
├── go.mod                   # Go module definition
└── README.md                # This file
```

## Building and Running

### Prerequisites
- Go 1.19 or later

### Build
```bash
make build
```

### Run Tests
```bash
make test
```

### Run the Application
```bash
make run
# or
./my_program
```

## Usage

The system supports the following commands:

### Create Parking Lot
```
create_parking_lot <capacity>
```
Example: `create_parking_lot 6`

### Park a Vehicle
```
park <registration_number> <color>
```
Example: `park KA01HH1234 White`

### Leave a Parking Slot
```
leave <slot_number>
```
Example: `leave 4`

### Check Status
```
status
```
Shows all occupied slots with vehicle details.

### Find Slot by Registration Number
```
slot_number_for_registration_number <registration_number>
```
Example: `slot_number_for_registration_number KA01HH3141`

## Example Session

```
$ ./my_program
create_parking_lot 6
Created a parking lot with 6 slots
park KA01HH1234 White
Allocated slot number: 1
park KA01HH9999 White
Allocated slot number: 2
park KA01BB0001 Black
Allocated slot number: 3
park KA01HH7777 Red
Allocated slot number: 4
park KA01HH2701 Blue
Allocated slot number: 5
park KA01HH3141 Black
Allocated slot number: 6
leave 4
Slot number 4 is free
status
Slot No.	Registration No	Colour
1		KA01HH1234	White
2		KA01HH9999	White
3		KA01BB0001	Black
5		KA01HH2701	Blue
6		KA01HH3141	Black
park KA01P333 White
Allocated slot number: 4
park DL12AA9999 White
Sorry, parking lot is full
slot_number_for_registration_number KA01HH3141
6
slot_number_for_registration_number MH04AY1111
Not found
```

## Architecture

The system follows object-oriented design principles with clear separation of concerns:

- **Vehicle**: Represents a vehicle with registration number and color
- **Slot**: Represents a parking slot that can be occupied or free
- **ParkingLot**: Manages the collection of slots and parking operations
- **Shell**: Provides the interactive command-line interface
- **TelemetryProvider**: Handles OpenTelemetry configuration and initialization
- **InstrumentedParkingLot**: Wraps ParkingLot with custom metrics and tracing
- **InstrumentedShell**: Wraps Shell with telemetry instrumentation

The parking lot automatically assigns the nearest available slot to the entry point (lowest numbered slot).

## OpenTelemetry Instrumentation

The application includes comprehensive OpenTelemetry instrumentation with **custom metrics and traces** (no auto-instrumentation):

### Custom Metrics

1. **parking_operations_total** (Counter): Total number of parking operations
   - Labels: operation, vehicle_color, status, allocated_slot

2. **leaving_operations_total** (Counter): Total number of leaving operations  
   - Labels: operation, slot_number, status, vehicle_registration, vehicle_color

3. **parking_lot_occupancy** (UpDownCounter): Current number of occupied slots
   - Tracks real-time occupancy changes

4. **operation_duration_seconds** (Histogram): Duration of parking lot operations
   - Labels: operation, status, and operation-specific attributes
   - Measures response times for all operations

5. **parking_lot_total_slots** (UpDownCounter): Total parking lot capacity
   - Set once during parking lot creation

### Custom Traces

All operations are traced with detailed spans containing:

- **Operation context**: Registration numbers, colors, slot numbers
- **Events**: Key operation milestones (slot_allocated, vehicle_found, etc.)
- **Attributes**: Detailed metadata about vehicles and operations
- **Error handling**: Failed operations are marked with error status
- **Span relationships**: Command processing → operation execution hierarchy

### Telemetry Output

- **Traces**: Exported to OTLP HTTP endpoint (`{endpoint}/v1/traces`)
- **Metrics**: Exported every 5 seconds to OTLP HTTP endpoint (`{endpoint}/v1/metrics`)
- **Resource attributes**: Service name and version identification
- **Graceful shutdown**: Proper telemetry cleanup on application exit

### OTLP Configuration

The application supports configurable OTLP endpoints:

**Default endpoint (localhost):**
```bash
./my_program
```
Uses `http://localhost:4318` as the default OTLP endpoint.

**Custom OTLP endpoint:**
```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318 ./my_program
```

**Docker Compose with Jaeger:**
```bash
# Example docker-compose setup
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:14268 ./my_program
```

The telemetry data provides complete visibility into parking lot operations, performance metrics, and system behavior for monitoring and observability. Data is sent via OTLP HTTP protocol to your observability backend (Jaeger, Grafana, DataDog, etc.).