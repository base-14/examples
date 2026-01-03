# Security Advisory - php8-laravel8-sqlite

## ⚠️ Known Security Vulnerabilities

**Last Updated:** 2025-11-23
**Status:** NOT RECOMMENDED FOR PRODUCTION USE

This project uses **Laravel 8.x**, which reached End-of-Life (EOL) on
July 26, 2023. It contains **19+ known security vulnerabilities** across
8 packages that cannot be fully resolved without upgrading to Laravel 9+.

## Vulnerability Summary

| Severity | Count | Packages Affected                                    |
|----------|-------|------------------------------------------------------|
| High     | 10    | guzzlehttp/guzzle, symfony/process, league/flysystem |
| Medium   | 6     | symfony/http-foundation, symfony/http-kernel, yaml   |
| Low      | 3     | symfony/http-foundation, symfony/routing             |

## Critical Vulnerabilities

### Guzzlehttp/Guzzle - 5 High Severity Issues

- **CVE-2022-31091**: Change in port should be considered a change in origin
- **CVE-2022-31090**: CURLOPT_HTTPAUTH option not cleared on change of origin
- **CVE-2022-31043**: Failure to strip Authorization header on HTTP downgrade
- **CVE-2022-31042**: Failure to strip Cookie header on change in host or
  HTTP downgrade
- **CVE-2022-29248**: Cross-domain cookie leakage

**Current Version:** 7.10.0
**Impact:** Potential credential leakage, cross-domain attacks
**Note:** These vulnerabilities are tied to Laravel 8.x framework constraints

### Symfony Components - 14 Various Severities

#### symfony/http-foundation (5.4.50)

- **CVE-2024-50345** (Low): Open redirect via browser-sanitized URLs
- **CVE-2024-50342** (Medium): Possible session fixation
- **CVE-2023-47090** (Medium): Session fixation
- **CVE-2023-46733** (Medium): Untrusted X-Forwarded-Host may inject internal
  URLs
- **CVE-2022-24895** (Medium): Session fixation when using explicit scheme

#### symfony/http-kernel (5.4.50)

- **CVE-2024-50340** (Medium): Session fixation
- **CVE-2023-46735** (Medium): Possible session fixation via X-Forwarded-Prefix
  header
- **CVE-2022-24894** (Medium): Cookie headers stored in HttpCache
- **CVE-2021-41267** (Medium): Webcache poisoning via X-Forwarded-Prefix

#### symfony/process (5.4.47)

- **CVE-2024-51736** (High): Command execution hijack on Windows

#### symfony/routing

- **CVE-2024-50342** (Medium): Possible session fixation
- **CVE-2020-15094** (Medium): Authentication bypass

#### symfony/yaml

- **CVE-2021-21424** (Medium): Command execution via Yaml parsing

### Other Packages

- **league/flysystem** (1.1.10): CVE-2021-32708 (High) - Path traversal
  vulnerability

## Why These Can't Be Fixed

Laravel 8.x reached End-of-Life in July 2023:

- Requires Symfony 5.x components (also EOL)
- Updating Symfony to 6.x/7.x breaks Laravel 8.x compatibility
- No security patches released for Laravel 8.x

## Current Package Versions

| Package | Version | Status |
| ------- | ------- | ------ |
| PHP | 8.1 | ✅ Supported |
| laravel/framework | 8.83 (dev) | ⚠️ EOL |
| guzzlehttp/guzzle | 7.10.0 | ⚠️ Vulnerable |
| symfony/http-foundation | 5.4.50 | ⚠️ EOL |
| symfony/http-kernel | 5.4.50 | ⚠️ EOL |
| symfony/process | 5.4.47 | ⚠️ EOL |

## Recommended Action

**Migrate to Laravel 11+** with PHP 8.3+ for:

- Active security support (until September 2026)
- Latest stable dependencies
- Zero known vulnerabilities

## For Development/Testing Only

This project is suitable for:

- ✅ Local development and testing
- ✅ Learning Laravel concepts
- ✅ Non-production experiments

**DO NOT use in production** for:

- ❌ Sensitive user data
- ❌ Financial transactions
- ❌ Public-facing applications
- ❌ Critical authentication/authorization

## Run Security Audit

```bash
docker exec laravel-app composer audit
```

## References

- [Laravel 8.x Release Notes](https://laravel.com/docs/8.x/releases)
- [Guzzle Security Advisories](https://github.com/guzzle/guzzle/security/advisories)
- [Symfony Security](https://symfony.com/security)
