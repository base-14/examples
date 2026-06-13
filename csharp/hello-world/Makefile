.PHONY: build run clean format lint check

build:
	dotnet build

run:
	dotnet run

clean:
	dotnet clean

format:
	dotnet format

lint:
	dotnet format --verify-no-changes

check:
	dotnet build
	dotnet format --verify-no-changes

.DEFAULT_GOAL := build
