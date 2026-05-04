// Composes cluster + identity + rbac modules.

targetScope = 'resourceGroup'

@description('Short name suffix used to derive cluster + UAMI names.')
param namePrefix string = 'base14-aks-otel-op'

@description('Azure region. Defaults to the resource group region.')
param location string = resourceGroup().location

@description('Kubernetes version (minor).')
param kubernetesVersion string = '1.35'

@description('VM size for the system node pool.')
param systemNodeSize string = 'Standard_B4s_v2'

@description('System node pool node count (validation pins 1).')
@minValue(1)
@maxValue(3)
param systemNodeCount int = 1

@description('K8s namespace for OTel ServiceAccounts.')
param serviceAccountNamespace string = 'otel'

@description('K8s ServiceAccount names. One federated credential per name. The operator creates each SA from the OpenTelemetryCollector CR.')
param serviceAccountNames array = [
  'otel-agent'
  'otel-cluster'
  'otel-control-plane'
]

@description('Built-in role: Monitoring Reader.')
param monitoringReaderRoleId string = '43d0d8ad-25c7-4714-9337-8ba259a9fe05'

module cluster 'modules/cluster.bicep' = {
  name: 'aks-cluster'
  params: {
    name: 'aks-${namePrefix}'
    location: location
    kubernetesVersion: kubernetesVersion
    systemNodeSize: systemNodeSize
    systemNodeCount: systemNodeCount
  }
}

module identity 'modules/identity.bicep' = {
  name: 'aks-identity'
  params: {
    name: 'id-${namePrefix}'
    location: location
    aksOidcIssuer: cluster.outputs.oidcIssuerUrl
    serviceAccountNamespace: serviceAccountNamespace
    serviceAccountNames: serviceAccountNames
  }
}

module rbacMonitoringReader 'modules/rbac.bicep' = {
  name: 'rbac-monitoring-reader'
  params: {
    principalId: identity.outputs.principalId
    roleDefinitionId: monitoringReaderRoleId
  }
}

output clusterName string = cluster.outputs.clusterName
output clusterResourceId string = cluster.outputs.clusterResourceId
output oidcIssuerUrl string = cluster.outputs.oidcIssuerUrl
output uamiName string = identity.outputs.identityName
output uamiPrincipalId string = identity.outputs.principalId
output uamiClientId string = identity.outputs.clientId
output serviceAccountNamespace string = serviceAccountNamespace
output serviceAccountNames array = serviceAccountNames
