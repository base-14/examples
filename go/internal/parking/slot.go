package parking

type Slot struct {
	Number     int
	IsOccupied bool
	Vehicle    *Vehicle
}

func NewSlot(number int) *Slot {
	return &Slot{
		Number:     number,
		IsOccupied: false,
		Vehicle:    nil,
	}
}

func (s *Slot) Park(vehicle *Vehicle) {
	s.Vehicle = vehicle
	s.IsOccupied = true
}

func (s *Slot) Leave() *Vehicle {
	vehicle := s.Vehicle
	s.Vehicle = nil
	s.IsOccupied = false
	return vehicle
}