package parking

import "testing"

func TestNewSlot(t *testing.T) {
	slotNumber := 1
	slot := NewSlot(slotNumber)
	
	if slot.Number != slotNumber {
		t.Errorf("Expected slot number %d, got %d", slotNumber, slot.Number)
	}
	
	if slot.IsOccupied {
		t.Error("Expected new slot to be unoccupied")
	}
	
	if slot.Vehicle != nil {
		t.Error("Expected new slot to have no vehicle")
	}
}

func TestSlotPark(t *testing.T) {
	slot := NewSlot(1)
	vehicle := NewVehicle("KA01HH1234", "White")
	
	slot.Park(vehicle)
	
	if !slot.IsOccupied {
		t.Error("Expected slot to be occupied after parking")
	}
	
	if slot.Vehicle != vehicle {
		t.Error("Expected slot to contain the parked vehicle")
	}
}

func TestSlotLeave(t *testing.T) {
	slot := NewSlot(1)
	vehicle := NewVehicle("KA01HH1234", "White")
	
	slot.Park(vehicle)
	leavingVehicle := slot.Leave()
	
	if slot.IsOccupied {
		t.Error("Expected slot to be unoccupied after leaving")
	}
	
	if slot.Vehicle != nil {
		t.Error("Expected slot to have no vehicle after leaving")
	}
	
	if leavingVehicle != vehicle {
		t.Error("Expected leaving vehicle to be the same as parked vehicle")
	}
}