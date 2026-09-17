CREATE TABLE IF NOT EXISTS bookings (
    booking_ref TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    travel_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'cancelled',
    rebooked_flight_id TEXT,
    hotel_id TEXT
);

CREATE TABLE IF NOT EXISTS flight_alternatives (
    flight_id TEXT PRIMARY KEY,
    booking_ref TEXT NOT NULL REFERENCES bookings (booking_ref),
    price INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS hotel_options (
    hotel_id TEXT PRIMARY KEY,
    booking_ref TEXT NOT NULL REFERENCES bookings (booking_ref),
    city TEXT NOT NULL,
    price INTEGER NOT NULL
);
