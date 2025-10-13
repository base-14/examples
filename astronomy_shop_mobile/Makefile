.PHONY: help clean get build run test analyze format check-format install-ios install-android run-ios run-android build-ios build-android build-all test-unit test-widget test-integration

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

clean: ## Clean build artifacts and dependencies
	flutter clean
	rm -rf build/
	rm -rf .dart_tool/
	rm -rf .packages
	rm -f pubspec.lock

get: ## Get dependencies
	flutter pub get

build: ## Build debug APK for Android
	flutter build apk --debug

run: ## Run app on connected device/emulator
	flutter run -d chrome --web-browser-flag="--disable-web-security" \
	--web-browser-flag="--disable-features=VizDisplayCompositor" \
	--web-hostname localhost --web-port 8090
test: ## Run all tests
	flutter test

analyze: ## Run static analysis
	flutter analyze

format: ## Format code
	dart format .

check-format: ## Check code formatting
	dart format --set-exit-if-changed .

install-ios: ## Install iOS dependencies (CocoaPods)
	cd ios && pod install

install-android: ## Install Android dependencies
	cd android && ./gradlew dependencies

run-ios: ## Run on iOS simulator
	flutter run -d ios

run-android: ## Run on Android emulator
	flutter run -d android

build-ios: ## Build iOS app (requires Mac with Xcode)
	flutter build ios --release

build-android: ## Build Android release APK
	flutter build apk --release

build-all: build-android build-ios ## Build for all platforms

test-unit: ## Run unit tests only
	flutter test test/unit/

test-widget: ## Run widget tests only
	flutter test test/widget/

test-integration: ## Run integration tests
	flutter test integration_test/

dev: ## Run app with hot reload
	flutter run --hot

web: ## Run app in web browser
	flutter run -d chrome

profile: ## Run app in profile mode
	flutter run --profile

release: ## Run app in release mode
	flutter run --release

doctor: ## Check Flutter environment
	flutter doctor -v

upgrade: ## Upgrade Flutter and packages
	flutter upgrade
	flutter pub upgrade

outdated: ## Check for outdated packages
	flutter pub outdated

coverage: ## Generate test coverage report
	flutter test --coverage
	@echo "Coverage report generated in coverage/lcov.info"

watch: ## Watch for changes and run tests
	find lib test -name '*.dart' | entr -c flutter test