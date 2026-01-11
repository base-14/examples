# Test script for .NET ASP.NET Core SQL Server API
# Usage: .\scripts\test-api.ps1 [-BaseUrl "http://localhost:8080"]

param(
    [string]$BaseUrl = "http://localhost:8080"
)

$ErrorActionPreference = "Stop"
$script:Pass = 0
$script:Fail = 0

function Write-Pass {
    param([string]$Message)
    Write-Host "√ PASS: $Message" -ForegroundColor Green
    $script:Pass++
}

function Write-Fail {
    param([string]$Message)
    Write-Host "X FAIL: $Message" -ForegroundColor Red
    $script:Fail++
}

function Write-Info {
    param([string]$Message)
    Write-Host "→ $Message" -ForegroundColor Yellow
}

function Test-Endpoint {
    param(
        [string]$Method,
        [string]$Endpoint,
        [int]$ExpectedStatus,
        [string]$Data = $null,
        [string]$Auth = $null,
        [string]$Description
    )

    Write-Info "Testing: $Description"

    $headers = @{}
    if ($Data) {
        $headers["Content-Type"] = "application/json"
    }
    if ($Auth) {
        $headers["Authorization"] = "Bearer $Auth"
    }

    try {
        $params = @{
            Method = $Method
            Uri = "$BaseUrl$Endpoint"
            Headers = $headers
            ErrorAction = "Stop"
        }

        if ($Data) {
            $params["Body"] = $Data
        }

        $response = Invoke-WebRequest @params -SkipHttpErrorCheck
        $statusCode = $response.StatusCode

        if ($statusCode -eq $ExpectedStatus) {
            Write-Pass "$Description (status: $statusCode)"
            if ($response.Content) {
                Write-Host $response.Content
            }
        } else {
            Write-Fail "$Description (expected: $ExpectedStatus, got: $statusCode)"
            if ($response.Content) {
                Write-Host $response.Content
            }
        }
    }
    catch {
        Write-Fail "$Description (error: $_)"
    }

    Write-Host ""
}

function Get-JsonValue {
    param(
        [string]$Json,
        [string]$Property
    )
    try {
        $obj = $Json | ConvertFrom-Json
        return $obj.$Property
    }
    catch {
        return $null
    }
}

Write-Host "========================================"
Write-Host ".NET ASP.NET Core SQL Server API Test Suite"
Write-Host "Base URL: $BaseUrl"
Write-Host "========================================"
Write-Host ""

# Health Check
Test-Endpoint -Method "GET" -Endpoint "/api/health" -ExpectedStatus 200 -Description "Health check"

# Register User
$Timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$UserEmail = "test$Timestamp@example.com"
$UserData = @{
    email = $UserEmail
    password = "password123"
    name = "Test User"
} | ConvertTo-Json

Write-Info "Registering user: $UserEmail"
try {
    $registerResponse = Invoke-WebRequest -Method POST -Uri "$BaseUrl/api/register" `
        -Headers @{"Content-Type" = "application/json"} `
        -Body $UserData -SkipHttpErrorCheck

    $Token = Get-JsonValue -Json $registerResponse.Content -Property "token"

    if ($Token) {
        Write-Pass "User registration"
        Write-Host "Token received: $($Token.Substring(0, [Math]::Min(20, $Token.Length)))..."
    } else {
        Write-Fail "User registration - no token received"
        Write-Host $registerResponse.Content
    }
}
catch {
    Write-Fail "User registration - error: $_"
}
Write-Host ""

# Login
Write-Info "Testing login"
$LoginData = @{
    email = $UserEmail
    password = "password123"
} | ConvertTo-Json

try {
    $loginResponse = Invoke-WebRequest -Method POST -Uri "$BaseUrl/api/login" `
        -Headers @{"Content-Type" = "application/json"} `
        -Body $LoginData -SkipHttpErrorCheck

    $LoginToken = Get-JsonValue -Json $loginResponse.Content -Property "token"

    if ($LoginToken) {
        Write-Pass "User login"
    } else {
        Write-Fail "User login - no token received"
    }
}
catch {
    Write-Fail "User login - error: $_"
}
Write-Host ""

# Get User Profile
Test-Endpoint -Method "GET" -Endpoint "/api/user" -ExpectedStatus 200 -Auth $Token -Description "Get user profile (authenticated)"

# Get User Profile - Unauthorized
Test-Endpoint -Method "GET" -Endpoint "/api/user" -ExpectedStatus 401 -Description "Get user profile (unauthorized)"

# Create Article
$ArticleData = @{
    title = "Test Article $Timestamp"
    description = "Test description"
    body = "This is the article body."
} | ConvertTo-Json

Write-Info "Creating article"
try {
    $createResponse = Invoke-WebRequest -Method POST -Uri "$BaseUrl/api/articles" `
        -Headers @{"Content-Type" = "application/json"; "Authorization" = "Bearer $Token"} `
        -Body $ArticleData -SkipHttpErrorCheck

    $ArticleSlug = Get-JsonValue -Json $createResponse.Content -Property "slug"

    if ($ArticleSlug) {
        Write-Pass "Create article"
        Write-Host "Article slug: $ArticleSlug"
    } else {
        Write-Fail "Create article - no slug received"
        Write-Host $createResponse.Content
    }
}
catch {
    Write-Fail "Create article - error: $_"
}
Write-Host ""

# List Articles
Test-Endpoint -Method "GET" -Endpoint "/api/articles" -ExpectedStatus 200 -Description "List articles (public)"

# Get Single Article
if ($ArticleSlug) {
    Test-Endpoint -Method "GET" -Endpoint "/api/articles/$ArticleSlug" -ExpectedStatus 200 -Description "Get single article"
}

# Update Article
if ($ArticleSlug) {
    $UpdateData = @{
        title = "Updated Article $Timestamp"
        description = "Updated description"
    } | ConvertTo-Json

    Write-Info "Updating article"
    try {
        $updateResponse = Invoke-WebRequest -Method PUT -Uri "$BaseUrl/api/articles/$ArticleSlug" `
            -Headers @{"Content-Type" = "application/json"; "Authorization" = "Bearer $Token"} `
            -Body $UpdateData -SkipHttpErrorCheck

        $NewSlug = Get-JsonValue -Json $updateResponse.Content -Property "slug"

        if ($NewSlug) {
            Write-Pass "Update article (owner)"
            Write-Host "New slug: $NewSlug"
            $ArticleSlug = $NewSlug
        } else {
            Write-Fail "Update article - no slug received"
            Write-Host $updateResponse.Content
        }
    }
    catch {
        Write-Fail "Update article - error: $_"
    }
    Write-Host ""
}

# Favorite Article
if ($ArticleSlug) {
    Test-Endpoint -Method "POST" -Endpoint "/api/articles/$ArticleSlug/favorite" -ExpectedStatus 200 -Auth $Token -Description "Favorite article"
}

# Unfavorite Article
if ($ArticleSlug) {
    Test-Endpoint -Method "DELETE" -Endpoint "/api/articles/$ArticleSlug/favorite" -ExpectedStatus 200 -Auth $Token -Description "Unfavorite article"
}

# Delete Article
if ($ArticleSlug) {
    Test-Endpoint -Method "DELETE" -Endpoint "/api/articles/$ArticleSlug" -ExpectedStatus 204 -Auth $Token -Description "Delete article (owner)"
}

# Logout
Test-Endpoint -Method "POST" -Endpoint "/api/logout" -ExpectedStatus 200 -Auth $Token -Description "Logout"

Write-Host ""
Write-Host "========================================"
Write-Host "Error Scenarios"
Write-Host "========================================"
Write-Host ""

# Login with invalid credentials
$InvalidLogin = '{"email":"invalid@test.com","password":"wrongpass"}'
Test-Endpoint -Method "POST" -Endpoint "/api/login" -ExpectedStatus 401 -Data $InvalidLogin -Description "Login with invalid credentials"

# Duplicate registration
Test-Endpoint -Method "POST" -Endpoint "/api/register" -ExpectedStatus 409 -Data $UserData -Description "Duplicate email registration"

# Get non-existent article
Test-Endpoint -Method "GET" -Endpoint "/api/articles/non-existent-slug-12345" -ExpectedStatus 404 -Description "Get non-existent article"

# Create article without auth
$NoAuthArticle = '{"title":"Test","description":"Test","body":"Test"}'
Test-Endpoint -Method "POST" -Endpoint "/api/articles" -ExpectedStatus 401 -Data $NoAuthArticle -Description "Create article without auth"

# Register second user for authorization tests
$User2Email = "user2_$Timestamp@example.com"
$User2Data = @{
    email = $User2Email
    password = "password123"
    name = "User 2"
} | ConvertTo-Json

Write-Info "Registering second user for auth tests"
try {
    $user2Response = Invoke-WebRequest -Method POST -Uri "$BaseUrl/api/register" `
        -Headers @{"Content-Type" = "application/json"} `
        -Body $User2Data -SkipHttpErrorCheck

    $Token2 = Get-JsonValue -Json $user2Response.Content -Property "token"

    if ($Token2) {
        Write-Pass "Second user registration"
    } else {
        Write-Fail "Second user registration - no token received"
    }
}
catch {
    Write-Fail "Second user registration - error: $_"
}
Write-Host ""

# Create article as user 1 for authorization tests
$Article2Data = @{
    title = "Auth Test Article $Timestamp"
    description = "For auth testing"
    body = "Body content"
} | ConvertTo-Json

Write-Info "Creating article as user 1"
try {
    $create2Response = Invoke-WebRequest -Method POST -Uri "$BaseUrl/api/articles" `
        -Headers @{"Content-Type" = "application/json"; "Authorization" = "Bearer $Token"} `
        -Body $Article2Data -SkipHttpErrorCheck

    $Article2Slug = Get-JsonValue -Json $create2Response.Content -Property "slug"

    if ($Article2Slug) {
        Write-Pass "Create article for auth tests"
        Write-Host "Article slug: $Article2Slug"
    } else {
        Write-Fail "Create article for auth tests - no slug received"
    }
}
catch {
    Write-Fail "Create article for auth tests - error: $_"
}
Write-Host ""

# Update article as different user (should fail)
if ($Article2Slug -and $Token2) {
    Test-Endpoint -Method "PUT" -Endpoint "/api/articles/$Article2Slug" -ExpectedStatus 403 -Data '{"title":"Hacked"}' -Auth $Token2 -Description "Update article as non-owner (forbidden)"
}

# Delete article as different user (should fail)
if ($Article2Slug -and $Token2) {
    Test-Endpoint -Method "DELETE" -Endpoint "/api/articles/$Article2Slug" -ExpectedStatus 403 -Auth $Token2 -Description "Delete article as non-owner (forbidden)"
}

# Favorite non-existent article
Test-Endpoint -Method "POST" -Endpoint "/api/articles/non-existent-slug/favorite" -ExpectedStatus 404 -Auth $Token -Description "Favorite non-existent article"

# Cleanup: delete the auth test article
if ($Article2Slug) {
    Test-Endpoint -Method "DELETE" -Endpoint "/api/articles/$Article2Slug" -ExpectedStatus 204 -Auth $Token -Description "Cleanup: delete auth test article"
}

# Summary
Write-Host "========================================"
Write-Host "Test Summary"
Write-Host "========================================"
Write-Host "Passed: $script:Pass" -ForegroundColor Green
Write-Host "Failed: $script:Fail" -ForegroundColor Red
Write-Host ""

if ($script:Fail -gt 0) {
    exit 1
}
