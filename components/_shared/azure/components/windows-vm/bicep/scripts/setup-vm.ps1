$ErrorActionPreference = 'Stop'

# Pinned sha256 of otelcol-contrib_0.152.0_windows_amd64.tar.gz, sourced from
# https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.152.0/opentelemetry-collector-releases_otelcol-contrib_windows_checksums.txt
# Source-pin (not runtime-fetch) so a compromised release can't fool us — bumping
# the version requires editing this file AND committing the new hash.
$otelVersion = '0.152.0'
$expectedSha256 = '0542223c2882edf41e6fd2c036772a9cb41c6f192335d577e3a0cab3c5a39d2b'

# 1. Install IIS.
Install-WindowsFeature -Name Web-Server -IncludeManagementTools
Get-WindowsFeature -Name Web-Server | Out-File C:\iis-install.log

# 2. Download otelcol-contrib, verify sha256, extract.
$installDir = 'C:\Program Files\OtelCollector'
$zipUrl = "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v$otelVersion/otelcol-contrib_${otelVersion}_windows_amd64.tar.gz"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
$archive = "$installDir\otelcol.tar.gz"
Invoke-WebRequest -Uri $zipUrl -OutFile $archive
$actualSha256 = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLower()
if ($actualSha256 -ne $expectedSha256) {
  Remove-Item $archive -Force -ErrorAction SilentlyContinue
  throw "otelcol-contrib checksum mismatch: expected $expectedSha256, got $actualSha256. Refusing to install."
}
# Tarball is flat (otelcol-contrib.exe + README.md at root), no nesting to flatten.
tar -xzf $archive -C $installDir
Remove-Item $archive

# 3. Drop the idle config. Placeholders are replaced by the wire-up script
#    once the central collector is up.
#    NOTE: tls.insecure is true here only because the central collector's TLS
#    posture is a chart-design-time decision. The wire-up step is responsible
#    for switching to insecure:false + ca_file once the chart exposes its CA.
#    Until then, bearer travels cleartext over the LB's public endpoint --
#    acceptable only for an 8h dev substrate.
$configPath = "$installDir\config.yaml"
@'
receivers:
  iis:
    collection_interval: 60s
processors:
  batch: {}
exporters:
  otlp:
    endpoint: ${env:OTLP_GATEWAY_ENDPOINT}
    tls:
      insecure: true
    headers:
      authorization: "Bearer ${env:OTLP_GATEWAY_TOKEN}"
extensions: {}
service:
  pipelines:
    metrics:
      receivers: [iis]
      processors: [batch]
      exporters: [otlp]
'@ | Out-File -FilePath $configPath -Encoding UTF8

# 4. Register Windows service via New-Service (handles binPath quoting natively;
#    sc.exe binPath= with spaces in PowerShell mangles the path).
#    Service env defaults set OTLP_GATEWAY_* to placeholders so the exporter
#    fails closed; the wire-up script overwrites them and restarts the service.
$svcName = 'OtelCollector'
$binaryPath = "`"$installDir\otelcol-contrib.exe`" --config=`"$configPath`""
# Idempotency guard: CustomScriptExtension is one-shot at provision, but an
# operator manual re-invoke would otherwise hit New-Service's "service already
# exists" error. Remove-Service is PS 6+, so use sc.exe on Server 2022 (PS 5.1).
if (Get-Service -Name $svcName -ErrorAction SilentlyContinue) {
  Stop-Service -Name $svcName -ErrorAction SilentlyContinue
  & sc.exe delete $svcName | Out-Null
  Start-Sleep -Seconds 2
}
New-Service -Name $svcName `
  -BinaryPathName $binaryPath `
  -StartupType Automatic `
  -DisplayName 'OpenTelemetry Collector (IIS forwarder)'
[Environment]::SetEnvironmentVariable('OTLP_GATEWAY_ENDPOINT', 'PLACEHOLDER:4317', 'Machine')
[Environment]::SetEnvironmentVariable('OTLP_GATEWAY_TOKEN', 'PLACEHOLDER', 'Machine')
Start-Service -Name $svcName
