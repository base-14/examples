package parking

type Vehicle struct {
	RegistrationNumber string
	Color              string
}

func NewVehicle(registrationNumber, color string) *Vehicle {
	return &Vehicle{
		RegistrationNumber: registrationNumber,
		Color:              color,
	}
}
