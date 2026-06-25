.PHONY: clean reset

clean:
	cd app && ./gradlew clean
	cd notify && ./gradlew clean

reset:
	docker compose down -v --remove-orphans
