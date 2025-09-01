package parking

import "testing"

func TestNewVehicle(t *testing.T) {
	regNumber := "KA01HH1234"
	color := "White"
	
	vehicle := NewVehicle(regNumber, color)
	
	if vehicle.RegistrationNumber != regNumber {
		t.Errorf("Expected registration number %s, got %s", regNumber, vehicle.RegistrationNumber)
	}
	
	if vehicle.Color != color {
		t.Errorf("Expected color %s, got %s", color, vehicle.Color)
	}
}