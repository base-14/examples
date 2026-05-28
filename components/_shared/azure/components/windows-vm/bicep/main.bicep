targetScope = 'resourceGroup'

param namePrefix string = 'b14-winvm'
param location string = resourceGroup().location
param vmSize string = 'Standard_D2s_v3'
@secure()
param adminPassword string
@description('Operator public IP for the NSG RDP rule.')
param operatorPublicIp string
@description('Public URL to setup-vm.ps1 fetched by CustomScriptExtension.')
param setupScriptUri string

module vm 'modules/vm.bicep' = {
  name: 'windows-vm'
  params: {
    name: namePrefix
    location: location
    vmSize: vmSize
    adminPassword: adminPassword
    operatorPublicIp: operatorPublicIp
  }
}

module setup 'modules/customscript.bicep' = {
  name: 'setup-iis-otel'
  params: {
    vmName: vm.outputs.vmName
    location: location
    setupScriptUri: setupScriptUri
  }
}

output vmName string = vm.outputs.vmName
