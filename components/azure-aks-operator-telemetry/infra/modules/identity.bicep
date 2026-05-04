// User-assigned Managed Identity + 3 federated credentials, one per
// operator-managed ServiceAccount (otel-agent, otel-cluster, otel-control-plane).
// The operator creates each SA from the OpenTelemetryCollector spec.serviceAccount;
// provision.sh annotates them with the UAMI client-id post-create so the
// workload-identity webhook injects the projected token.

@description('Name for the User-assigned Managed Identity.')
param name string

@description('Azure region (must match the AKS cluster region).')
param location string

@description('AKS cluster OIDC issuer URL (output of cluster.bicep).')
param aksOidcIssuer string

@description('Kubernetes namespace that hosts the OTel ServiceAccounts.')
param serviceAccountNamespace string = 'otel'

@description('Kubernetes ServiceAccount names that need federated tokens.')
param serviceAccountNames array = [
  'otel-agent'
  'otel-cluster'
  'otel-control-plane'
]

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
}

// One federated credential per ServiceAccount. ARM rejects concurrent creates
// against the same parent UAMI; @batchSize(1) serializes the loop.
@batchSize(1)
resource fedCreds 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = [for sa in serviceAccountNames: {
  name: 'fc-${sa}'
  parent: uami
  properties: {
    issuer: aksOidcIssuer
    subject: 'system:serviceaccount:${serviceAccountNamespace}:${sa}'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}]

output identityId string = uami.id
output principalId string = uami.properties.principalId
output clientId string = uami.properties.clientId
output identityName string = uami.name
