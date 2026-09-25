\connect kyc

-- Invented names. "Alexander Petrov Wolkov" is a near match for the applicant in
-- fixtures/partial_sanctions_match/id.txt. "Nadia Karim Haddad" is an exact match for the
-- screen_sanctions integration test.
INSERT INTO sanctions (full_name, country) VALUES
    ('Alexander Petrov Wolkov', 'RU'),
    ('Nadia Karim Haddad', 'LB'),
    ('Chen Wei Ming', 'CN'),
    ('Katarzyna Nowak-Zielinska', 'PL'),
    ('Tomas Novak', 'CZ');
