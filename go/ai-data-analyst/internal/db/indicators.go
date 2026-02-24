package db

import (
	"context"
)

type Indicator struct {
	ID          int    `json:"id"`
	Name        string `json:"name"`
	Code        string `json:"code"`
	Category    string `json:"category"`
	Unit        string `json:"unit"`
	Description string `json:"description"`
}

func ListIndicators(ctx context.Context, q Querier) ([]Indicator, error) {
	rows, err := q.Query(ctx,
		"SELECT id, name, code, category, unit, COALESCE(description, '') FROM indicators ORDER BY category, name",
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var indicators []Indicator
	for rows.Next() {
		var i Indicator
		if err := rows.Scan(&i.ID, &i.Name, &i.Code, &i.Category, &i.Unit, &i.Description); err != nil {
			return nil, err
		}
		indicators = append(indicators, i)
	}
	return indicators, rows.Err()
}

func GetIndicatorByCode(ctx context.Context, q Querier, code string) (*Indicator, error) {
	var i Indicator
	err := q.QueryRow(ctx,
		"SELECT id, name, code, category, unit, COALESCE(description, '') FROM indicators WHERE code = $1", code,
	).Scan(&i.ID, &i.Name, &i.Code, &i.Category, &i.Unit, &i.Description)
	if err != nil {
		return nil, err
	}
	return &i, nil
}

func SearchIndicators(ctx context.Context, q Querier, term string) ([]Indicator, error) {
	rows, err := q.Query(ctx,
		"SELECT id, name, code, category, unit, COALESCE(description, '') FROM indicators WHERE LOWER(name) LIKE LOWER($1) OR LOWER(code) LIKE LOWER($1) ORDER BY name",
		"%"+term+"%",
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var indicators []Indicator
	for rows.Next() {
		var i Indicator
		if err := rows.Scan(&i.ID, &i.Name, &i.Code, &i.Category, &i.Unit, &i.Description); err != nil {
			return nil, err
		}
		indicators = append(indicators, i)
	}
	return indicators, rows.Err()
}
