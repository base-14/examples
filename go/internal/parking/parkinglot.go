package parking

import (
	"fmt"
	"sort"
)

type ParkingLot struct {
	capacity int
	slots    []*Slot
}

func NewParkingLot(capacity int) *ParkingLot {
	slots := make([]*Slot, capacity)
	for i := 0; i < capacity; i++ {
		slots[i] = NewSlot(i + 1)
	}
	
	return &ParkingLot{
		capacity: capacity,
		slots:    slots,
	}
}

func (pl *ParkingLot) Park(registrationNumber, color string) (int, error) {
	for _, slot := range pl.slots {
		if !slot.IsOccupied {
			vehicle := NewVehicle(registrationNumber, color)
			slot.Park(vehicle)
			return slot.Number, nil
		}
	}
	return 0, fmt.Errorf("parking lot is full")
}

func (pl *ParkingLot) Leave(slotNumber int) error {
	if slotNumber < 1 || slotNumber > pl.capacity {
		return fmt.Errorf("invalid slot number")
	}
	
	slot := pl.slots[slotNumber-1]
	if !slot.IsOccupied {
		return fmt.Errorf("slot is already empty")
	}
	
	slot.Leave()
	return nil
}

func (pl *ParkingLot) GetStatus() []*Slot {
	var occupiedSlots []*Slot
	for _, slot := range pl.slots {
		if slot.IsOccupied {
			occupiedSlots = append(occupiedSlots, slot)
		}
	}
	
	sort.Slice(occupiedSlots, func(i, j int) bool {
		return occupiedSlots[i].Number < occupiedSlots[j].Number
	})
	
	return occupiedSlots
}

func (pl *ParkingLot) GetSlotByRegistrationNumber(registrationNumber string) (int, error) {
	for _, slot := range pl.slots {
		if slot.IsOccupied && slot.Vehicle.RegistrationNumber == registrationNumber {
			return slot.Number, nil
		}
	}
	return 0, fmt.Errorf("not found")
}