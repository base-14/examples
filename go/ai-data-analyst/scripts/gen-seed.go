//go:build ignore
// +build ignore

package main

import (
	"fmt"
	"math"
	"math/rand"
	"os"
	"strings"
)

type country struct {
	Name, Code, Region, IncomeGroup string
}

type indicator struct {
	Name, Code, Category, Unit, Description string
}

type countryProfile struct {
	GDPpc0    float64 // GDP per capita base (2003)
	Pop0      float64 // Population base (2003)
	LE0       float64 // Life expectancy base
	CO2       float64 // CO2 per capita base
	Internet0 float64 // Internet % base (2003)
	Unemp     float64 // Unemployment base
	Growth    float64 // avg GDP growth
	Urban0    float64 // Urban population %
	Poverty0  float64 // Poverty %
	Forest0   float64 // Forest %
}

var countries = []country{
	{"United States", "USA", "North America", "High income"},
	{"China", "CHN", "East Asia & Pacific", "Upper middle income"},
	{"India", "IND", "South Asia", "Lower middle income"},
	{"United Kingdom", "GBR", "Europe & Central Asia", "High income"},
	{"Germany", "DEU", "Europe & Central Asia", "High income"},
	{"Japan", "JPN", "East Asia & Pacific", "High income"},
	{"Brazil", "BRA", "Latin America & Caribbean", "Upper middle income"},
	{"Nigeria", "NGA", "Sub-Saharan Africa", "Lower middle income"},
	{"South Africa", "ZAF", "Sub-Saharan Africa", "Upper middle income"},
	{"Australia", "AUS", "East Asia & Pacific", "High income"},
	{"Korea, Rep.", "KOR", "East Asia & Pacific", "High income"},
	{"Mexico", "MEX", "Latin America & Caribbean", "Upper middle income"},
	{"Indonesia", "IDN", "East Asia & Pacific", "Upper middle income"},
	{"Turkey", "TUR", "Europe & Central Asia", "Upper middle income"},
	{"Saudi Arabia", "SAU", "Middle East & North Africa", "High income"},
	{"United Arab Emirates", "ARE", "Middle East & North Africa", "High income"},
	{"Singapore", "SGP", "East Asia & Pacific", "High income"},
	{"Norway", "NOR", "Europe & Central Asia", "High income"},
	{"Sweden", "SWE", "Europe & Central Asia", "High income"},
	{"Switzerland", "CHE", "Europe & Central Asia", "High income"},
	{"Canada", "CAN", "North America", "High income"},
	{"France", "FRA", "Europe & Central Asia", "High income"},
	{"Italy", "ITA", "Europe & Central Asia", "High income"},
	{"Spain", "ESP", "Europe & Central Asia", "High income"},
	{"Russian Federation", "RUS", "Europe & Central Asia", "Upper middle income"},
	{"Argentina", "ARG", "Latin America & Caribbean", "Upper middle income"},
	{"Colombia", "COL", "Latin America & Caribbean", "Upper middle income"},
	{"Egypt, Arab Rep.", "EGY", "Middle East & North Africa", "Lower middle income"},
	{"Kenya", "KEN", "Sub-Saharan Africa", "Lower middle income"},
	{"Ethiopia", "ETH", "Sub-Saharan Africa", "Low income"},
	{"Bangladesh", "BGD", "South Asia", "Lower middle income"},
	{"Pakistan", "PAK", "South Asia", "Lower middle income"},
	{"Vietnam", "VNM", "East Asia & Pacific", "Lower middle income"},
	{"Thailand", "THA", "East Asia & Pacific", "Upper middle income"},
	{"Malaysia", "MYS", "East Asia & Pacific", "Upper middle income"},
	{"Philippines", "PHL", "East Asia & Pacific", "Lower middle income"},
	{"Poland", "POL", "Europe & Central Asia", "High income"},
	{"Netherlands", "NLD", "Europe & Central Asia", "High income"},
	{"Belgium", "BEL", "Europe & Central Asia", "High income"},
	{"Austria", "AUT", "Europe & Central Asia", "High income"},
	{"Israel", "ISR", "Middle East & North Africa", "High income"},
	{"Chile", "CHL", "Latin America & Caribbean", "High income"},
	{"Peru", "PER", "Latin America & Caribbean", "Upper middle income"},
	{"Morocco", "MAR", "Middle East & North Africa", "Lower middle income"},
	{"Ghana", "GHA", "Sub-Saharan Africa", "Lower middle income"},
	{"Tanzania", "TZA", "Sub-Saharan Africa", "Low income"},
	{"Ukraine", "UKR", "Europe & Central Asia", "Lower middle income"},
	{"Romania", "ROU", "Europe & Central Asia", "Upper middle income"},
	{"Czech Republic", "CZE", "Europe & Central Asia", "High income"},
	{"New Zealand", "NZL", "East Asia & Pacific", "High income"},
}

var indicators = []indicator{
	{"GDP growth (annual %)", "NY.GDP.MKTP.KD.ZG", "Economic", "%", "Annual percentage growth rate of GDP at market prices based on constant local currency"},
	{"GDP per capita (current US$)", "NY.GDP.PCAP.CD", "Economic", "USD", "GDP per capita is gross domestic product divided by midyear population"},
	{"Population, total", "SP.POP.TOTL", "Social", "persons", "Total population based on the de facto definition of population"},
	{"Life expectancy at birth, total (years)", "SP.DYN.LE00.IN", "Social", "years", "Number of years a newborn infant would live if prevailing patterns of mortality were to stay the same"},
	{"Death rate, crude (per 1,000 people)", "SP.DYN.CDRT.IN", "Social", "per 1,000 people", "Crude death rate indicates the number of deaths per 1,000 people"},
	{"Government expenditure on education, total (% of GDP)", "SE.XPD.TOTL.GD.ZS", "Social", "%", "General government expenditure on education as a percentage of GDP"},
	{"Current health expenditure (% of GDP)", "SH.XPD.CHEX.GD.ZS", "Social", "%", "Level of current health expenditure expressed as a percentage of GDP"},
	{"CO2 emissions (metric tons per capita)", "EN.ATM.CO2E.PC", "Environmental", "metric tons", "Carbon dioxide emissions from burning fossil fuels and manufacturing cement"},
	{"Electric power consumption (kWh per capita)", "EG.USE.ELEC.KH.PC", "Environmental", "kWh", "Electric power consumption measures the production of power plants and combined heat and power plants"},
	{"Individuals using the Internet (% of population)", "IT.NET.USER.ZS", "Technology", "%", "Individuals who have used the Internet in the last 3 months"},
	{"Unemployment, total (% of total labor force)", "SL.UEM.TOTL.ZS", "Economic", "%", "Unemployment refers to the share of the labor force that is without work"},
	{"Inflation, consumer prices (annual %)", "FP.CPI.TOTL.ZG", "Economic", "%", "Inflation measured by the consumer price index"},
	{"Trade (% of GDP)", "NE.TRD.GNFS.ZS", "Economic", "%", "Trade is the sum of exports and imports of goods and services measured as a share of GDP"},
	{"Foreign direct investment, net inflows (% of GDP)", "BX.KLT.DINV.WD.GD.ZS", "Economic", "%", "Foreign direct investment are the net inflows of investment"},
	{"Central government debt, total (% of GDP)", "GC.DOD.TOTL.GD.ZS", "Economic", "%", "Debt is the entire stock of direct government fixed-term obligations to others"},
	{"Poverty headcount ratio at national poverty lines (% of population)", "SI.POV.NAHC", "Social", "%", "National poverty headcount ratio is the percentage of the population living below the national poverty lines"},
	{"Forest area (% of land area)", "AG.LND.FRST.ZS", "Environmental", "%", "Forest area is land under natural or planted stands of trees of at least 5 meters in situ"},
	{"Urban population (% of total population)", "SP.URB.TOTL.IN.ZS", "Social", "%", "Urban population refers to people living in urban areas"},
	{"Gross savings (% of GDP)", "NY.GNS.ICTR.ZS", "Economic", "%", "Gross savings are calculated as gross national income less total consumption plus net transfers"},
	{"Military expenditure (% of GDP)", "MS.MIL.XPND.GD.ZS", "Economic", "%", "Military expenditures data from SIPRI"},
}

var profiles = map[string]countryProfile{
	"USA": {39000, 290e6, 77.0, 19.5, 62, 5.5, 2.2, 79, 12.0, 33},
	"CHN": {1300, 1290e6, 72.0, 3.5, 6, 4.5, 9.5, 40, 28.0, 21},
	"IND": {550, 1080e6, 63.5, 1.0, 4, 5.0, 7.0, 28, 38.0, 23},
	"GBR": {30000, 59.5e6, 78.0, 9.0, 65, 5.0, 2.0, 80, 14.0, 12},
	"DEU": {30000, 82.5e6, 78.5, 10.5, 61, 5.0, 1.5, 75, 11.0, 32},
	"JPN": {33500, 127.5e6, 82.0, 9.5, 64, 4.5, 1.2, 86, 14.0, 67},
	"BRA": {3000, 181e6, 71.0, 1.8, 13, 6.0, 3.0, 83, 25.0, 60},
	"NGA": {500, 131e6, 47.0, 0.6, 4, 5.0, 6.0, 35, 64.0, 25},
	"ZAF": {3500, 46.5e6, 52.0, 8.5, 8, 8.0, 3.5, 59, 40.0, 7},
	"AUS": {28000, 20e6, 80.0, 17.5, 63, 5.0, 3.0, 87, 12.0, 16},
	"KOR": {14000, 48e6, 77.0, 9.5, 65, 3.5, 4.5, 80, 15.0, 64},
	"MEX": {6500, 103e6, 74.0, 3.8, 14, 4.0, 2.5, 75, 42.0, 34},
	"IDN": {1000, 222e6, 66.5, 1.3, 4, 5.0, 5.0, 43, 37.0, 52},
	"TUR": {4500, 67e6, 72.0, 3.2, 14, 6.0, 5.5, 65, 23.0, 13},
	"SAU": {12000, 23.5e6, 73.0, 15.0, 19, 6.0, 4.0, 80, 0.0, 1},
	"ARE": {33000, 3.5e6, 76.0, 25.0, 30, 3.0, 5.0, 82, 0.0, 4},
	"SGP": {25000, 4.2e6, 79.0, 12.0, 62, 3.5, 5.0, 100, 0.0, 23},
	"NOR": {50000, 4.6e6, 79.5, 11.0, 78, 3.5, 2.0, 77, 10.0, 33},
	"SWE": {38000, 9.0e6, 80.0, 6.0, 79, 5.5, 2.5, 84, 10.0, 69},
	"CHE": {48000, 7.3e6, 81.0, 6.0, 65, 3.0, 2.5, 74, 8.0, 31},
	"CAN": {28000, 31.5e6, 79.5, 17.0, 64, 5.5, 2.5, 80, 12.0, 38},
	"FRA": {29000, 60.5e6, 79.0, 6.5, 39, 5.5, 1.5, 77, 12.0, 31},
	"ITA": {27000, 57.5e6, 80.0, 7.8, 35, 4.5, 0.5, 68, 12.0, 34},
	"ESP": {21000, 42e6, 79.5, 7.5, 40, 4.0, 3.0, 77, 14.0, 36},
	"RUS": {3000, 144e6, 65.0, 10.5, 13, 6.0, 6.5, 73, 21.0, 49},
	"ARG": {3800, 38e6, 74.5, 3.8, 15, 5.0, 3.0, 89, 32.0, 10},
	"COL": {2300, 42.5e6, 72.0, 1.5, 8, 5.5, 4.0, 72, 48.0, 55},
	"EGY": {1100, 71e6, 69.5, 2.0, 6, 5.5, 4.5, 43, 22.0, 0},
	"KEN": {500, 34e6, 52.0, 0.3, 5, 7.0, 5.0, 21, 45.0, 7},
	"ETH": {120, 73e6, 53.0, 0.08, 0.2, 6.0, 8.0, 15, 77.0, 14},
	"BGD": {400, 137e6, 65.0, 0.25, 1, 4.5, 6.0, 25, 40.0, 11},
	"PAK": {550, 150e6, 63.5, 0.7, 5, 5.0, 5.0, 34, 32.0, 3},
	"VNM": {500, 80e6, 73.0, 0.8, 8, 5.5, 6.5, 26, 40.0, 42},
	"THA": {2300, 64.5e6, 72.5, 3.3, 15, 3.5, 5.0, 33, 14.0, 37},
	"MYS": {4500, 25e6, 73.5, 6.5, 40, 3.5, 5.5, 64, 12.0, 66},
	"PHL": {1000, 83e6, 67.5, 0.9, 5, 4.5, 5.0, 47, 33.0, 24},
	"POL": {5500, 38.2e6, 74.5, 7.5, 28, 6.0, 3.5, 62, 18.0, 30},
	"NLD": {35000, 16.2e6, 78.5, 11.0, 70, 5.0, 1.5, 77, 10.0, 11},
	"BEL": {31000, 10.4e6, 78.0, 11.0, 54, 6.5, 1.5, 97, 8.0, 22},
	"AUT": {33000, 8.1e6, 79.0, 8.5, 55, 5.5, 1.5, 66, 10.0, 47},
	"ISR": {18000, 6.7e6, 80.0, 10.0, 28, 4.5, 2.5, 91, 12.0, 7},
	"CHL": {4800, 16e6, 77.0, 3.5, 31, 4.5, 4.0, 87, 20.0, 21},
	"PER": {2300, 27e6, 72.0, 1.2, 12, 4.5, 5.5, 59, 45.0, 53},
	"MAR": {1700, 30e6, 69.0, 1.3, 20, 5.5, 4.5, 55, 14.0, 12},
	"GHA": {380, 20.5e6, 57.5, 0.35, 2, 6.0, 5.5, 34, 40.0, 23},
	"TZA": {320, 37e6, 52.0, 0.1, 1, 5.0, 6.5, 23, 60.0, 52},
	"UKR": {1000, 47.5e6, 68.0, 6.5, 5, 6.5, 7.0, 67, 25.0, 17},
	"ROU": {2700, 21.8e6, 71.5, 4.5, 12, 5.0, 5.0, 53, 25.0, 28},
	"CZE": {10000, 10.2e6, 75.5, 11.5, 40, 4.0, 3.0, 74, 8.0, 34},
	"NZL": {22000, 4.1e6, 79.0, 8.5, 62, 4.0, 3.5, 86, 10.0, 31},
}

func main() {
	rng := rand.New(rand.NewSource(42))
	var b strings.Builder

	b.WriteString("-- World Bank Seed Data\n-- Generated for ai-data-analyst example\n-- 50 countries, 20 indicators, years 2003-2023\n\n")

	// Countries
	b.WriteString("-- Countries\n")
	for _, c := range countries {
		fmt.Fprintf(&b, "INSERT INTO countries (name, code, region, income_group) VALUES ('%s', '%s', '%s', '%s') ON CONFLICT DO NOTHING;\n",
			escape(c.Name), c.Code, c.Region, c.IncomeGroup)
	}

	b.WriteString("\n-- Indicators\n")
	for _, i := range indicators {
		fmt.Fprintf(&b, "INSERT INTO indicators (name, code, category, unit, description) VALUES ('%s', '%s', '%s', '%s', '%s') ON CONFLICT DO NOTHING;\n",
			escape(i.Name), i.Code, i.Category, i.Unit, escape(i.Description))
	}

	b.WriteString("\n-- Indicator values\n")
	b.WriteString("INSERT INTO indicator_values (country_id, indicator_id, year, value)\nSELECT c.id, i.id, v.year, v.value::numeric\nFROM (VALUES\n")

	first := true
	for _, c := range countries {
		p := profiles[c.Code]
		for year := 2003; year <= 2023; year++ {
			yr := year - 2003
			yrf := float64(yr)

			// GDP growth
			growth := p.Growth + rng.Float64()*2 - 1
			if year == 2009 {
				growth = -3.5 + rng.Float64()*3
			}
			if year == 2020 {
				growth = -4.0 + rng.Float64()*3
			}
			if year == 2021 {
				growth = 4.0 + rng.Float64()*4
			}
			writeVal(&b, &first, rng, c.Code, "NY.GDP.MKTP.KD.ZG", year, round2(growth))

			// GDP per capita
			gdppc := p.GDPpc0 * math.Pow(1+p.Growth/100, yrf)
			gdppc *= 1 + (rng.Float64()*0.06 - 0.03)
			writeVal(&b, &first, rng, c.Code, "NY.GDP.PCAP.CD", year, round2(gdppc))

			// Population
			popGrowth := 0.01 + rng.Float64()*0.005
			if c.Code == "JPN" || c.Code == "DEU" || c.Code == "ITA" || c.Code == "UKR" {
				popGrowth = -0.002
			}
			pop := p.Pop0 * math.Pow(1+popGrowth, yrf)
			writeVal(&b, &first, rng, c.Code, "SP.POP.TOTL", year, round0(pop))

			// Life expectancy
			le := p.LE0 + yrf*0.15 + rng.Float64()*0.5 - 0.25
			if year == 2020 {
				le -= 1.0 + rng.Float64()
			}
			writeVal(&b, &first, rng, c.Code, "SP.DYN.LE00.IN", year, round2(le))

			// Death rate
			dr := 8.0 + rng.Float64()*2
			if p.LE0 < 60 {
				dr = 12.0 + rng.Float64()*3
			}
			if p.LE0 > 78 {
				dr = 7.0 + rng.Float64()*2
			}
			dr -= yrf * 0.05
			if year == 2020 {
				dr += 1.5
			}
			writeVal(&b, &first, rng, c.Code, "SP.DYN.CDRT.IN", year, round2(clamp(dr, 2, 20)))

			// Education expenditure
			edu := 4.0 + rng.Float64()*2.5
			if c.IncomeGroup == "High income" {
				edu = 4.5 + rng.Float64()*2
			}
			writeVal(&b, &first, rng, c.Code, "SE.XPD.TOTL.GD.ZS", year, round2(edu))

			// Health expenditure
			health := 5.0 + rng.Float64()*3
			if c.IncomeGroup == "High income" {
				health = 7.0 + rng.Float64()*5
			}
			if c.IncomeGroup == "Low income" {
				health = 3.0 + rng.Float64()*2
			}
			writeVal(&b, &first, rng, c.Code, "SH.XPD.CHEX.GD.ZS", year, round2(health))

			// CO2 emissions
			co2 := p.CO2*(1+yrf*0.01) + rng.Float64()*0.5 - 0.25
			if c.IncomeGroup == "High income" && year > 2015 {
				co2 *= 0.97
			}
			writeVal(&b, &first, rng, c.Code, "EN.ATM.CO2E.PC", year, round2(clamp(co2, 0.05, 30)))

			// Electric power consumption
			elec := 1000.0 + p.GDPpc0*0.25 + yrf*100
			elec += rng.Float64()*200 - 100
			writeVal(&b, &first, rng, c.Code, "EG.USE.ELEC.KH.PC", year, round0(clamp(elec, 50, 25000)))

			// Internet usage
			inet := p.Internet0 + yrf*3.5
			if inet > 98 {
				inet = 95 + rng.Float64()*4
			}
			inet += rng.Float64()*2 - 1
			writeVal(&b, &first, rng, c.Code, "IT.NET.USER.ZS", year, round2(clamp(inet, 0.1, 99.5)))

			// Unemployment
			unemp := p.Unemp + rng.Float64()*1.5 - 0.75
			if year == 2009 {
				unemp += 2.5
			}
			if year == 2020 {
				unemp += 3.0
			}
			if year == 2021 {
				unemp -= 1.0
			}
			writeVal(&b, &first, rng, c.Code, "SL.UEM.TOTL.ZS", year, round2(clamp(unemp, 1, 35)))

			// Inflation
			infl := 2.5 + rng.Float64()*2
			if c.IncomeGroup == "Lower middle income" {
				infl = 5 + rng.Float64()*4
			}
			if c.IncomeGroup == "Low income" {
				infl = 6 + rng.Float64()*5
			}
			if year == 2022 {
				infl += 4.0
			}
			writeVal(&b, &first, rng, c.Code, "FP.CPI.TOTL.ZG", year, round2(infl))

			// Trade % GDP
			trade := 50 + rng.Float64()*30
			if c.Code == "SGP" || c.Code == "ARE" || c.Code == "BEL" || c.Code == "NLD" {
				trade = 120 + rng.Float64()*80
			}
			if c.Code == "USA" || c.Code == "BRA" || c.Code == "JPN" {
				trade = 25 + rng.Float64()*15
			}
			writeVal(&b, &first, rng, c.Code, "NE.TRD.GNFS.ZS", year, round2(trade))

			// FDI % GDP
			fdi := 1.5 + rng.Float64()*3
			if c.Code == "SGP" || c.Code == "ARE" {
				fdi = 5 + rng.Float64()*10
			}
			writeVal(&b, &first, rng, c.Code, "BX.KLT.DINV.WD.GD.ZS", year, round2(fdi))

			// Government debt % GDP
			debt := 40 + rng.Float64()*30
			if c.Code == "JPN" {
				debt = 170 + yrf*4
			}
			if c.Code == "USA" {
				debt = 60 + yrf*3
			}
			if year >= 2020 {
				debt += 15
			}
			writeVal(&b, &first, rng, c.Code, "GC.DOD.TOTL.GD.ZS", year, round2(debt))

			// Poverty
			pov := p.Poverty0*math.Pow(0.96, yrf) + rng.Float64()*2 - 1
			if year == 2020 {
				pov += 3
			}
			writeVal(&b, &first, rng, c.Code, "SI.POV.NAHC", year, round2(clamp(pov, 0.5, 80)))

			// Forest area
			forest := p.Forest0 - yrf*0.1 + rng.Float64()*0.3 - 0.15
			writeVal(&b, &first, rng, c.Code, "AG.LND.FRST.ZS", year, round2(clamp(forest, 0, 90)))

			// Urban population
			urban := p.Urban0 + yrf*0.4 + rng.Float64()*0.3
			writeVal(&b, &first, rng, c.Code, "SP.URB.TOTL.IN.ZS", year, round2(clamp(urban, 10, 100)))

			// Gross savings
			savings := 20 + rng.Float64()*10
			if c.Code == "CHN" || c.Code == "SGP" {
				savings = 35 + rng.Float64()*15
			}
			if c.Code == "SAU" || c.Code == "NOR" {
				savings = 30 + rng.Float64()*15
			}
			writeVal(&b, &first, rng, c.Code, "NY.GNS.ICTR.ZS", year, round2(savings))

			// Military expenditure
			mil := 1.5 + rng.Float64()*1
			if c.Code == "USA" || c.Code == "SAU" || c.Code == "ISR" {
				mil = 3.0 + rng.Float64()*2
			}
			if c.Code == "RUS" {
				mil = 3.5 + rng.Float64()*1.5
			}
			writeVal(&b, &first, rng, c.Code, "MS.MIL.XPND.GD.ZS", year, round2(mil))
		}
	}

	b.WriteString("\n) AS v(country_code, indicator_code, year, value)\n")
	b.WriteString("JOIN countries c ON c.code = v.country_code\n")
	b.WriteString("JOIN indicators i ON i.code = v.indicator_code\n")
	b.WriteString("ON CONFLICT DO NOTHING;\n")

	os.WriteFile("db/seed.sql", []byte(b.String()), 0644)
	fmt.Printf("Generated seed.sql: %d bytes\n", b.Len())
}

func writeVal(b *strings.Builder, first *bool, rng *rand.Rand, countryCode, indicatorCode string, year int, value float64) {
	// ~5% chance of NULL
	if rng.Float64() < 0.05 {
		return
	}
	if !*first {
		b.WriteString(",\n")
	}
	*first = false
	fmt.Fprintf(b, "  ('%s', '%s', %d, '%.6f')", countryCode, indicatorCode, year, value)
}

func round2(v float64) float64 { return math.Round(v*100) / 100 }
func round0(v float64) float64 { return math.Round(v) }
func clamp(v, min, max float64) float64 {
	if v < min {
		return min
	}
	if v > max {
		return max
	}
	return v
}
func escape(s string) string { return strings.ReplaceAll(s, "'", "''") }
