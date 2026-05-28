param vmName string
param location string
@description('URI to the setup-vm.ps1 script (publicly fetchable from a release tag or the examples repo raw URL).')
param setupScriptUri string

resource ext 'Microsoft.Compute/virtualMachines/extensions@2024-07-01' = {
  name: '${vmName}/InstallIISAndOtel'
  location: location
  properties: {
    publisher: 'Microsoft.Compute'
    type: 'CustomScriptExtension'
    typeHandlerVersion: '1.10'
    autoUpgradeMinorVersion: true
    settings: {
      commandToExecute: 'powershell -ExecutionPolicy Unrestricted -File setup-vm.ps1'
    }
    protectedSettings: {
      // fileUris in protectedSettings keeps the URL out of the activity log
      // and `az vm extension show` output. SHA-pinned GitHub raw URL has no
      // secret in it, but matches Microsoft's convention for fetch chains.
      fileUris: [ setupScriptUri ]
    }
  }
}

output extName string = ext.name
