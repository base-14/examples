package parking

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Shell struct {
	parkingLot *ParkingLot
	scanner    *bufio.Scanner
}

func NewShell() *Shell {
	return &Shell{
		scanner: bufio.NewScanner(os.Stdin),
	}
}

func (s *Shell) Run() {
	for {
		if !s.scanner.Scan() {
			break
		}

		input := strings.TrimSpace(s.scanner.Text())
		if input == "" {
			continue
		}

		s.processCommand(input)
	}
}

func (s *Shell) processCommand(input string) {
	parts := strings.Fields(input)
	if len(parts) == 0 {
		return
	}

	command := parts[0]

	switch command {
	case "create_parking_lot":
		s.handleCreateParkingLot(parts)
	case "park":
		s.handlePark(parts)
	case "leave":
		s.handleLeave(parts)
	case "status":
		s.handleStatus()
	case "slot_number_for_registration_number":
		s.handleSlotNumberForRegistrationNumber(parts)
	default:
		fmt.Printf("Unknown command: %s\n", command)
	}
}

func (s *Shell) handleCreateParkingLot(parts []string) {
	if len(parts) != 2 {
		fmt.Println("Usage: create_parking_lot <capacity>")
		return
	}

	capacity, err := strconv.Atoi(parts[1])
	if err != nil || capacity <= 0 {
		fmt.Println("Invalid capacity")
		return
	}

	s.parkingLot = NewParkingLot(capacity)
	fmt.Printf("Created a parking lot with %d slots\n", capacity)
}

func (s *Shell) handlePark(parts []string) {
	if s.parkingLot == nil {
		fmt.Println("Parking lot not created")
		return
	}

	if len(parts) != 3 {
		fmt.Println("Usage: park <registration_number> <color>")
		return
	}

	registrationNumber := parts[1]
	color := parts[2]

	slotNumber, err := s.parkingLot.Park(registrationNumber, color)
	if err != nil {
		fmt.Println("Sorry, parking lot is full")
		return
	}

	fmt.Printf("Allocated slot number: %d\n", slotNumber)
}

func (s *Shell) handleLeave(parts []string) {
	if s.parkingLot == nil {
		fmt.Println("Parking lot not created")
		return
	}

	if len(parts) != 2 {
		fmt.Println("Usage: leave <slot_number>")
		return
	}

	slotNumber, err := strconv.Atoi(parts[1])
	if err != nil {
		fmt.Println("Invalid slot number")
		return
	}

	err = s.parkingLot.Leave(slotNumber)
	if err != nil {
		fmt.Printf("Error: %s\n", err.Error())
		return
	}

	fmt.Printf("Slot number %d is free\n", slotNumber)
}

func (s *Shell) handleStatus() {
	if s.parkingLot == nil {
		fmt.Println("Parking lot not created")
		return
	}

	occupiedSlots := s.parkingLot.GetStatus()
	if len(occupiedSlots) == 0 {
		fmt.Println("Parking lot is empty")
		return
	}

	fmt.Println("Slot No.\tRegistration No\tColour")
	for _, slot := range occupiedSlots {
		fmt.Printf("%d\t\t%s\t%s\n", slot.Number, slot.Vehicle.RegistrationNumber, slot.Vehicle.Color)
	}
}

func (s *Shell) handleSlotNumberForRegistrationNumber(parts []string) {
	if s.parkingLot == nil {
		fmt.Println("Parking lot not created")
		return
	}

	if len(parts) != 2 {
		fmt.Println("Usage: slot_number_for_registration_number <registration_number>")
		return
	}

	registrationNumber := parts[1]

	slotNumber, err := s.parkingLot.GetSlotByRegistrationNumber(registrationNumber)
	if err != nil {
		fmt.Println("Not found")
		return
	}

	fmt.Printf("%d\n", slotNumber)
}
