ENV["BUNDLE_GEMFILE"] ||= File.expand_path("../Gemfile", __dir__)

# Load logger before Bundler to ensure the Logger constant is available
# for ActiveSupport::LoggerThreadSafeLevel in Rails 6.1. The logger gem
# is pinned to 1.4.3 (Ruby 3.0 default); loading it here prevents newer
# transitive versions from breaking the constant lookup at boot time.
require "logger"
require "bundler/setup"
