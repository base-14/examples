INSERT INTO bookings (booking_ref, origin, destination, travel_date)
VALUES
    ('BK-1001', 'LHR', 'BER', '2026-10-02'),
    ('BK-1002', 'LHR', 'JFK', '2026-10-02'),
    ('BK-1003', 'LHR', 'CDG', '2026-10-03')
ON CONFLICT (booking_ref) DO NOTHING;

-- Every alternative for a booking sits on one side of the 300 approval limit on
-- purpose: BK-1001 and BK-1003 are under it, BK-1002 is over it on every option.
INSERT INTO flight_alternatives (flight_id, booking_ref, price)
VALUES
    ('FL-201', 'BK-1001', 180),
    ('FL-202', 'BK-1001', 240),
    ('FL-301', 'BK-1002', 620),
    ('FL-302', 'BK-1002', 710),
    ('FL-401', 'BK-1003', 95)
ON CONFLICT (flight_id) DO NOTHING;

-- Hotel ids follow the destination airport code, e.g. HTL-BER for a BER booking.
INSERT INTO hotel_options (hotel_id, booking_ref, city, price)
VALUES
    ('HTL-BER', 'BK-1001', 'Berlin', 120),
    ('HTL-JFK', 'BK-1002', 'New York', 210),
    ('HTL-CDG', 'BK-1003', 'Paris', 140)
ON CONFLICT (hotel_id) DO NOTHING;
