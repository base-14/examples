package pipeline

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func testTracer() *sdktrace.TracerProvider {
	return sdktrace.NewTracerProvider()
}

func TestParseRanking(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "Top 10 countries by GDP growth in 2023")
	assert.Equal(t, "ranking", r.QuestionType)
	assert.Contains(t, r.Indicators, "NY.GDP.MKTP.KD.ZG")
	assert.NotNil(t, r.TimeRange)
	assert.Equal(t, 2023, r.TimeRange.StartYear)
}

func TestParseComparison(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "Compare GDP per capita between India and China from 2010 to 2020")
	assert.Equal(t, "comparison", r.QuestionType)
	assert.Contains(t, r.Countries, "IND")
	assert.Contains(t, r.Countries, "CHN")
	assert.Contains(t, r.Indicators, "NY.GDP.PCAP.CD")
	assert.NotNil(t, r.TimeRange)
	assert.Equal(t, 2010, r.TimeRange.StartYear)
	assert.Equal(t, 2020, r.TimeRange.EndYear)
}

func TestParseTrend(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "How has life expectancy changed in Japan over time?")
	assert.Equal(t, "trend", r.QuestionType)
	assert.Contains(t, r.Countries, "JPN")
	assert.Contains(t, r.Indicators, "SP.DYN.LE00.IN")
}

func TestParseAggregate(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "What is the average unemployment rate in Europe?")
	assert.Equal(t, "aggregate", r.QuestionType)
	assert.Contains(t, r.Indicators, "SL.UEM.TOTL.ZS")
}

func TestParseLookup(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "What is the population of Brazil?")
	assert.Equal(t, "lookup", r.QuestionType)
	assert.Contains(t, r.Countries, "BRA")
	assert.Contains(t, r.Indicators, "SP.POP.TOTL")
}

func TestParseNoEntities(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "Hello world")
	assert.Equal(t, "lookup", r.QuestionType)
	assert.Empty(t, r.Indicators)
	assert.Empty(t, r.Countries)
	assert.Nil(t, r.TimeRange)
}

func TestParseMultipleYears(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "CO2 emissions in Germany in 2005 and 2020")
	assert.Contains(t, r.Countries, "DEU")
	assert.Contains(t, r.Indicators, "EN.ATM.CO2E.PC")
	assert.NotNil(t, r.TimeRange)
	assert.Equal(t, 2005, r.TimeRange.StartYear)
	assert.Equal(t, 2020, r.TimeRange.EndYear)
}

func TestParseTimeRange(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "Internet usage from 2003 to 2023")
	assert.NotNil(t, r.TimeRange)
	assert.Equal(t, 2003, r.TimeRange.StartYear)
	assert.Equal(t, 2023, r.TimeRange.EndYear)
}

func TestParseMilitary(t *testing.T) {
	tp := testTracer()
	tracer := tp.Tracer("test")
	r := Parse(context.Background(), tracer, "Which countries have the highest military expenditure?")
	assert.Equal(t, "ranking", r.QuestionType)
	assert.Contains(t, r.Indicators, "MS.MIL.XPND.GD.ZS")
}
