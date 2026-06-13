.PHONY: build check clean run

build:
	mvn package -DskipTests -B

check:
	mvn verify -DskipTests -B

clean:
	mvn clean

run:
	mvn -q compile exec:java

.DEFAULT_GOAL := build
