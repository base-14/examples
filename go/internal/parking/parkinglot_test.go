package parking

import "testing"

func TestNewParkingLot(t *testing.T) {
	capacity := 6
	pl := NewParkingLot(capacity)
	
	if pl.capacity != capacity {
		t.Errorf("Expected capacity %d, got %d", capacity, pl.capacity)
	}
	
	if len(pl.slots) != capacity {
		t.Errorf("Expected %d slots, got %d", capacity, len(pl.slots))
	}
	
	for i, slot := range pl.slots {
		if slot.Number != i+1 {
			t.Errorf("Expected slot number %d, got %d", i+1, slot.Number)
		}
		if slot.IsOccupied {
			t.Errorf("Expected slot %d to be unoccupied", i+1)
		}
	}
}

func TestParkingLotPark(t *testing.T) {
	pl := NewParkingLot(3)
	
	slotNumber, err := pl.Park("KA01HH1234", "White")
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}
	if slotNumber != 1 {
		t.Errorf("Expected slot number 1, got %d", slotNumber)
	}
	
	slotNumber, err = pl.Park("KA01HH9999", "Black")
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}
	if slotNumber != 2 {
		t.Errorf("Expected slot number 2, got %d", slotNumber)
	}
	
	slotNumber, err = pl.Park("KA01BB0001", "Red")
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}
	if slotNumber != 3 {
		t.Errorf("Expected slot number 3, got %d", slotNumber)
	}
	
	_, err = pl.Park("KA01HH7777", "Blue")
	if err == nil {
		t.Error("Expected error when parking lot is full")
	}
}

func TestParkingLotLeave(t *testing.T) {
	pl := NewParkingLot(3)
	pl.Park("KA01HH1234", "White")
	pl.Park("KA01HH9999", "Black")
	
	err := pl.Leave(1)
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}
	
	if pl.slots[0].IsOccupied {
		t.Error("Expected slot 1 to be unoccupied after leaving")
	}
	
	slotNumber, err := pl.Park("KA01BB0001", "Red")
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}
	if slotNumber != 1 {
		t.Errorf("Expected to reuse slot 1, got slot %d", slotNumber)
	}
}

func TestParkingLotGetSlotByRegistrationNumber(t *testing.T) {
	pl := NewParkingLot(3)
	pl.Park("KA01HH1234", "White")
	pl.Park("KA01HH9999", "Black")
	
	slotNumber, err := pl.GetSlotByRegistrationNumber("KA01HH9999")
	if err != nil {
		t.Errorf("Unexpected error: %s", err.Error())
	}
	if slotNumber != 2 {
		t.Errorf("Expected slot number 2, got %d", slotNumber)
	}
	
	_, err = pl.GetSlotByRegistrationNumber("NOTFOUND")
	if err == nil {
		t.Error("Expected error for non-existent registration number")
	}
}

func TestParkingLotGetStatus(t *testing.T) {
	pl := NewParkingLot(6)
	pl.Park("KA01HH1234", "White")
	pl.Park("KA01HH9999", "White")
	pl.Park("KA01BB0001", "Black")
	pl.Park("KA01HH7777", "Red")
	pl.Park("KA01HH2701", "Blue")
	pl.Park("KA01HH3141", "Black")
	
	pl.Leave(4)
	
	status := pl.GetStatus()
	expectedSlots := []int{1, 2, 3, 5, 6}
	
	if len(status) != len(expectedSlots) {
		t.Errorf("Expected %d occupied slots, got %d", len(expectedSlots), len(status))
	}
	
	for i, slot := range status {
		if slot.Number != expectedSlots[i] {
			t.Errorf("Expected slot number %d at position %d, got %d", expectedSlots[i], i, slot.Number)
		}
	}
}