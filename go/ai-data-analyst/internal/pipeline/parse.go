package pipeline

import (
	"context"
	"regexp"
	"strconv"
	"strings"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

type Entity struct {
	Text     string `json:"text"`
	Type     string `json:"type"`
	Resolved string `json:"resolved"`
}

type TimeRange struct {
	StartYear int `json:"start_year"`
	EndYear   int `json:"end_year"`
}

type ParseResult struct {
	OriginalQuestion string     `json:"original_question"`
	Entities         []Entity   `json:"entities"`
	TimeRange        *TimeRange `json:"time_range"`
	QuestionType     string     `json:"question_type"`
	Indicators       []string   `json:"indicators"`
	Countries        []string   `json:"countries"`
}

var indicatorKeywords = map[string]string{
	"gdp growth":         "NY.GDP.MKTP.KD.ZG",
	"gdp per capita":     "NY.GDP.PCAP.CD",
	"population":         "SP.POP.TOTL",
	"life expectancy":    "SP.DYN.LE00.IN",
	"death rate":         "SP.DYN.CDRT.IN",
	"education":          "SE.XPD.TOTL.GD.ZS",
	"health expenditure": "SH.XPD.CHEX.GD.ZS",
	"co2":                "EN.ATM.CO2E.PC",
	"carbon":             "EN.ATM.CO2E.PC",
	"electricity":        "EG.USE.ELEC.KH.PC",
	"electric power":     "EG.USE.ELEC.KH.PC",
	"internet":           "IT.NET.USER.ZS",
	"unemployment":       "SL.UEM.TOTL.ZS",
	"inflation":          "FP.CPI.TOTL.ZG",
	"trade":              "NE.TRD.GNFS.ZS",
	"fdi":                "BX.KLT.DINV.WD.GD.ZS",
	"foreign direct":     "BX.KLT.DINV.WD.GD.ZS",
	"debt":               "GC.DOD.TOTL.GD.ZS",
	"poverty":            "SI.POV.NAHC",
	"forest":             "AG.LND.FRST.ZS",
	"urban":              "SP.URB.TOTL.IN.ZS",
	"savings":            "NY.GNS.ICTR.ZS",
	"military":           "MS.MIL.XPND.GD.ZS",
}

var countryKeywords = map[string]string{
	"united states": "USA", "us": "USA", "usa": "USA", "america": "USA",
	"china": "CHN", "india": "IND", "uk": "GBR", "united kingdom": "GBR",
	"germany": "DEU", "japan": "JPN", "brazil": "BRA", "nigeria": "NGA",
	"south africa": "ZAF", "australia": "AUS", "korea": "KOR", "south korea": "KOR",
	"mexico": "MEX", "indonesia": "IDN", "turkey": "TUR", "saudi arabia": "SAU",
	"uae": "ARE", "emirates": "ARE", "singapore": "SGP", "norway": "NOR",
	"sweden": "SWE", "switzerland": "CHE", "canada": "CAN", "france": "FRA",
	"italy": "ITA", "spain": "ESP", "russia": "RUS", "argentina": "ARG",
	"colombia": "COL", "egypt": "EGY", "kenya": "KEN", "ethiopia": "ETH",
	"bangladesh": "BGD", "pakistan": "PAK", "vietnam": "VNM", "thailand": "THA",
	"malaysia": "MYS", "philippines": "PHL", "poland": "POL", "netherlands": "NLD",
	"belgium": "BEL", "austria": "AUT", "israel": "ISR", "chile": "CHL",
	"peru": "PER", "morocco": "MAR", "ghana": "GHA", "tanzania": "TZA",
	"ukraine": "UKR", "romania": "ROU", "czech": "CZE", "new zealand": "NZL",
}

var yearPattern = regexp.MustCompile(`\b(19|20)\d{2}\b`)
var rangePattern = regexp.MustCompile(`\b((?:19|20)\d{2})\s*(?:-|to|through)\s*((?:19|20)\d{2})\b`)

func Parse(ctx context.Context, tracer trace.Tracer, question string) *ParseResult {
	ctx, span := tracer.Start(ctx, "pipeline_stage parse")
	defer span.End()

	result := &ParseResult{OriginalQuestion: question}
	lower := strings.ToLower(question)

	// Match indicators
	seen := map[string]bool{}
	for keyword, code := range indicatorKeywords {
		if strings.Contains(lower, keyword) && !seen[code] {
			seen[code] = true
			result.Indicators = append(result.Indicators, code)
			result.Entities = append(result.Entities, Entity{
				Text: keyword, Type: "indicator", Resolved: code,
			})
		}
	}

	// Match countries
	seenCountry := map[string]bool{}
	for keyword, code := range countryKeywords {
		if strings.Contains(lower, keyword) && !seenCountry[code] {
			seenCountry[code] = true
			result.Countries = append(result.Countries, code)
			result.Entities = append(result.Entities, Entity{
				Text: keyword, Type: "country", Resolved: code,
			})
		}
	}

	// Extract time range
	if m := rangePattern.FindStringSubmatch(question); m != nil {
		start, _ := strconv.Atoi(m[1])
		end, _ := strconv.Atoi(m[2])
		result.TimeRange = &TimeRange{StartYear: start, EndYear: end}
		result.Entities = append(result.Entities, Entity{
			Text: m[0], Type: "time_range", Resolved: m[0],
		})
	} else if years := yearPattern.FindAllString(question, -1); len(years) > 0 {
		for _, y := range years {
			yr, _ := strconv.Atoi(y)
			result.Entities = append(result.Entities, Entity{
				Text: y, Type: "year", Resolved: y,
			})
			if result.TimeRange == nil {
				result.TimeRange = &TimeRange{StartYear: yr, EndYear: yr}
			} else {
				if yr < result.TimeRange.StartYear {
					result.TimeRange.StartYear = yr
				}
				if yr > result.TimeRange.EndYear {
					result.TimeRange.EndYear = yr
				}
			}
		}
	}

	// Classify question type
	result.QuestionType = classifyQuestion(lower)

	span.SetAttributes(
		attribute.String("nlsql.stage", "parse"),
		attribute.String("nlsql.question_type", result.QuestionType),
		attribute.Int("nlsql.entities_found", len(result.Entities)),
		attribute.StringSlice("nlsql.indicators_matched", result.Indicators),
		attribute.StringSlice("nlsql.countries_matched", result.Countries),
	)
	if result.TimeRange != nil {
		span.SetAttributes(attribute.String("nlsql.time_range",
			strconv.Itoa(result.TimeRange.StartYear)+"-"+strconv.Itoa(result.TimeRange.EndYear)))
	}

	return result
}

func classifyQuestion(lower string) string {
	rankingWords := []string{"top", "highest", "lowest", "best", "worst", "most", "least", "rank", "leading"}
	for _, w := range rankingWords {
		if strings.Contains(lower, w) {
			return "ranking"
		}
	}

	comparisonWords := []string{"compare", "versus", "vs", "between", "difference"}
	for _, w := range comparisonWords {
		if strings.Contains(lower, w) {
			return "comparison"
		}
	}

	trendWords := []string{"trend", "over time", "change", "grew", "growth", "decline", "increased", "decreased", "from", "to"}
	for _, w := range trendWords {
		if strings.Contains(lower, w) {
			return "trend"
		}
	}

	aggregateWords := []string{"average", "total", "sum", "mean", "count", "how many"}
	for _, w := range aggregateWords {
		if strings.Contains(lower, w) {
			return "aggregate"
		}
	}

	return "lookup"
}
