package db

import (
	"context"
)

type Country struct {
	ID          int    `json:"id"`
	Name        string `json:"name"`
	Code        string `json:"code"`
	Region      string `json:"region"`
	IncomeGroup string `json:"income_group"`
}

func ListCountries(ctx context.Context, q Querier) ([]Country, error) {
	rows, err := q.Query(ctx, "SELECT id, name, code, region, income_group FROM countries ORDER BY name")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var countries []Country
	for rows.Next() {
		var c Country
		if err := rows.Scan(&c.ID, &c.Name, &c.Code, &c.Region, &c.IncomeGroup); err != nil {
			return nil, err
		}
		countries = append(countries, c)
	}
	return countries, rows.Err()
}

func GetCountryByCode(ctx context.Context, q Querier, code string) (*Country, error) {
	var c Country
	err := q.QueryRow(ctx,
		"SELECT id, name, code, region, income_group FROM countries WHERE code = $1", code,
	).Scan(&c.ID, &c.Name, &c.Code, &c.Region, &c.IncomeGroup)
	if err != nil {
		return nil, err
	}
	return &c, nil
}

func SearchCountries(ctx context.Context, q Querier, term string) ([]Country, error) {
	rows, err := q.Query(ctx,
		"SELECT id, name, code, region, income_group FROM countries WHERE LOWER(name) LIKE LOWER($1) ORDER BY name",
		"%"+term+"%",
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var countries []Country
	for rows.Next() {
		var c Country
		if err := rows.Scan(&c.ID, &c.Name, &c.Code, &c.Region, &c.IncomeGroup); err != nil {
			return nil, err
		}
		countries = append(countries, c)
	}
	return countries, rows.Err()
}
