# Security Advisory - ruby27-rails52-mysql8

## ⚠️ Known Security Vulnerabilities

**Last Updated:** 2026-01-03
**Status:** NOT RECOMMENDED FOR PRODUCTION USE

This project uses **Rails 5.2.8.1**, which reached End-of-Life (EOL) on
June 1, 2022, and **Ruby 2.7**, which reached EOL on March 31, 2023.
It contains known security vulnerabilities that cannot be fully resolved
without upgrading to Rails 6+.

## EOL Status

| Component | Version | EOL Date | Status |
|-----------|---------|----------|--------|
| Ruby | 2.7.x | March 31, 2023 | ⚠️ EOL |
| Rails | 5.2.8.1 | June 1, 2022 | ⚠️ EOL |
| MySQL | 8.x | Active | ✅ Supported |

## Why This Project Exists

This example demonstrates OpenTelemetry instrumentation patterns for
**legacy Rails 5.2 applications**. Many organizations still run Rails 5.2
in production and need observability solutions while planning upgrades.

## Known Vulnerability Categories

Rails 5.2.x is affected by multiple security vulnerabilities:

### Rails Framework Vulnerabilities

- **Session fixation attacks** - Multiple CVEs affecting session management
- **Cross-site scripting (XSS)** - Various XSS vulnerabilities in ActionView
- **SQL injection** - ActiveRecord vulnerabilities in certain edge cases
- **File disclosure** - Path traversal vulnerabilities in asset serving
- **CSRF token bypass** - Cross-site request forgery vulnerabilities
- **Regular expression denial of service (ReDoS)** - Various ReDoS vulnerabilities

### Dependency Vulnerabilities

Rails 5.2 relies on outdated gem versions with known issues:

- **Rack** - Multiple security fixes in newer versions
- **ActionPack** - Various HTTP header injection vulnerabilities
- **ActiveSupport** - XML parsing vulnerabilities (XXE)
- **Nokogiri** - XML/HTML parsing vulnerabilities (older versions)
- **Loofah** - HTML sanitization bypass vulnerabilities

## Why These Can't Be Fixed

Rails 5.2 reached End-of-Life in June 2022:

- No security patches released after EOL date
- Dependencies locked to old versions for compatibility
- Major architectural changes required to upgrade to Rails 6+
- Ruby 2.7 (also EOL) required for Rails 5.2 compatibility

## Recommended Action

**Migrate to Rails 8+** with Ruby 3.3+ for:

- Active security support (Rails 8.1 supported until 2027)
- Latest stable dependencies
- Improved performance and features
- Security patches and bug fixes

### Upgrade Path

1. **Rails 5.2 → 6.0** - Major version upgrade, requires code changes
2. **Rails 6.0 → 6.1** - Smaller migration
3. **Rails 6.1 → 7.0** - Requires Ruby 2.7+
4. **Rails 7.0 → 7.1** - Incremental upgrade
5. **Rails 7.1 → 8.0** - Latest stable version

See [Rails Upgrade Guide](https://guides.rubyonrails.org/upgrading_ruby_on_rails.html)

## For Development/Testing Only

This project is suitable for:

- ✅ Local development and testing
- ✅ Learning OpenTelemetry instrumentation patterns
- ✅ Testing observability solutions for legacy Rails apps
- ✅ Planning migration strategies from Rails 5.2

**DO NOT use in production** for:

- ❌ Sensitive user data
- ❌ Financial transactions
- ❌ Public-facing applications
- ❌ Critical authentication/authorization
- ❌ Any application requiring security compliance

## Run Security Audit

Check for known vulnerabilities:

```bash
# Install bundler-audit
gem install bundler-audit

# Audit Gemfile.lock
bundle audit check --update
```

## Migration Resources

- [Rails 5.2 Release Notes](https://guides.rubyonrails.org/5_2_release_notes.html)
- [Rails Security Policy](https://rubyonrails.org/security)
- [Ruby EOL Schedule](https://www.ruby-lang.org/en/downloads/branches/)
- [Rails Upgrade Checklist](https://railsdiff.org/)

## Current Example Purpose

This example shows:

- OpenTelemetry SDK integration with Rails 5.2
- Custom instrumentation for legacy Rails apps
- Distributed tracing with Sidekiq background jobs
- MySQL database query instrumentation
- Redis cache operation tracing

**Use for reference only** - Apply these patterns to your production
Rails 5.2 apps while planning your upgrade to a supported version.
