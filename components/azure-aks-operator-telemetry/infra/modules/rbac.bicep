// Generic RG-scope role assignment. Used by main.bicep to grant
// Monitoring Reader on the demo RG to the UAMI principal.

@description('Object ID of the principal receiving the role.')
param principalId string

@description('Built-in role definition GUID.')
param roleDefinitionId string

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, principalId, roleDefinitionId)
  scope: resourceGroup()
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roleDefinitionId
    )
  }
}
