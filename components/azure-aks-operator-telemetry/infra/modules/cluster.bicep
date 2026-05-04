// AKS cluster: system pool only, 1 x Standard_B4s_v2 (16 GB RAM headroom for
// cert-manager + operator + 3 collectors + KSM + 4 sample apps), Free-tier
// control plane. K8s 1.35.
// Workload Identity + OIDC issuer enabled (federated credentials in
// identity.bicep wire 3 K8s SAs to the UAMI for in-cluster collectors).

@description('AKS cluster name (DNS-safe, <= 63 chars).')
param name string

@description('Azure region.')
param location string

@description('Kubernetes version.')
param kubernetesVersion string = '1.35'

@description('VM size for the system node pool.')
param systemNodeSize string = 'Standard_B4s_v2'

@description('Node count. Validation pins to 1 (cost-deterministic); shipped customer doc recommends 1-2 for production.')
param systemNodeCount int = 1

resource aks 'Microsoft.ContainerService/managedClusters@2024-09-01' = {
  name: name
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Base'
    tier: 'Free'
  }
  properties: {
    kubernetesVersion: kubernetesVersion
    dnsPrefix: name
    enableRBAC: true
    oidcIssuerProfile: {
      enabled: true
    }
    securityProfile: {
      workloadIdentity: {
        enabled: true
      }
    }
    agentPoolProfiles: [
      {
        name: 'system'
        mode: 'System'
        count: systemNodeCount
        vmSize: systemNodeSize
        osType: 'Linux'
        osSKU: 'AzureLinux'
        type: 'VirtualMachineScaleSets'
        // Validation pins maxCount = minCount = 1 for cost determinism;
        // customer doc recommends maxCount: 2 in production so
        // cluster_autoscaler_* metrics have data.
        enableAutoScaling: true
        minCount: 1
        maxCount: 1
      }
    ]
    networkProfile: {
      networkPlugin: 'azure'
      loadBalancerSku: 'standard'
    }
  }
}

output clusterName string = aks.name
output clusterResourceId string = aks.id
output oidcIssuerUrl string = aks.properties.oidcIssuerProfile.issuerURL
output kubeletIdentityObjectId string = aks.properties.identityProfile.kubeletidentity.objectId
