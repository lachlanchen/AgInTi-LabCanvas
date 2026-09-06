param(
    [ValidateSet('Status', 'Enable', 'Disable')][string]$Mode = 'Status',
    [Parameter(Mandatory = $true)][string]$ExpectedComputer,
    [string]$UserName = $env:USERNAME
)

$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputer) {
    throw 'Refusing to configure a different Windows computer.'
}

# Winlogon consumes DefaultPassword from LSA; never put it in a registry value.
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security;

public static class LabCanvasAutologonSecret {
    [StructLayout(LayoutKind.Sequential)]
    struct UnicodeString {
        public ushort Length, MaximumLength;
        public IntPtr Buffer;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct ObjectAttributes {
        public uint Length;
        public IntPtr RootDirectory, ObjectName;
        public uint Attributes;
        public IntPtr SecurityDescriptor, SecurityQualityOfService;
    }
    [DllImport("advapi32.dll")]
    static extern uint LsaOpenPolicy(IntPtr system, ref ObjectAttributes attributes,
        uint access, out IntPtr policy);
    [DllImport("advapi32.dll")]
    static extern uint LsaStorePrivateData(IntPtr policy, ref UnicodeString name,
        ref UnicodeString data);
    [DllImport("advapi32.dll")]
    static extern uint LsaRetrievePrivateData(IntPtr policy, ref UnicodeString name,
        out IntPtr data);
    [DllImport("advapi32.dll")]
    static extern uint LsaFreeMemory(IntPtr data);
    [DllImport("advapi32.dll")]
    static extern uint LsaClose(IntPtr policy);
    [DllImport("advapi32.dll")]
    static extern uint LsaNtStatusToWinError(uint status);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool LogonUser(string user, string domain, IntPtr password,
        int logonType, int provider, out IntPtr token);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr token);

    static void Check(uint status) {
        if (status != 0) throw new Win32Exception((int)LsaNtStatusToWinError(status));
    }
    static IntPtr Open(uint access) {
        var attributes = new ObjectAttributes();
        attributes.Length = (uint)Marshal.SizeOf(typeof(ObjectAttributes));
        IntPtr policy;
        Check(LsaOpenPolicy(IntPtr.Zero, ref attributes, access, out policy));
        return policy;
    }
    static UnicodeString Name() {
        const string key = "DefaultPassword";
        return new UnicodeString {Length=(ushort)(key.Length*2),
            MaximumLength=(ushort)((key.Length+1)*2), Buffer=Marshal.StringToHGlobalUni(key)};
    }
    public static bool HasSecret() {
        IntPtr policy = Open(4), data = IntPtr.Zero;
        var name = Name();
        try {
            uint result = LsaRetrievePrivateData(policy, ref name, out data);
            if (result == 0xC0000034) return false;
            Check(result);
            var value = (UnicodeString)Marshal.PtrToStructure(data, typeof(UnicodeString));
            return value.Length > 0;
        } finally {
            if (data != IntPtr.Zero) LsaFreeMemory(data);
            Marshal.FreeHGlobal(name.Buffer);
            LsaClose(policy);
        }
    }
    public static void ValidateAndStore(string user, string domain, SecureString password) {
        if (password.Length == 0 || password.Length > 32766)
            throw new ArgumentException("Invalid password length.");
        IntPtr buffer = Marshal.SecureStringToGlobalAllocUnicode(password);
        IntPtr token = IntPtr.Zero, policy = IntPtr.Zero;
        var name = Name();
        try {
            if (!LogonUser(user, domain, buffer, 2, 0, out token))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            policy = Open(0x20);
            var value = new UnicodeString {Length=(ushort)(password.Length*2),
                MaximumLength=(ushort)((password.Length+1)*2), Buffer=buffer};
            Check(LsaStorePrivateData(policy, ref name, ref value));
        } finally {
            if (token != IntPtr.Zero) CloseHandle(token);
            if (policy != IntPtr.Zero) LsaClose(policy);
            Marshal.FreeHGlobal(name.Buffer);
            Marshal.ZeroFreeGlobalAllocUnicode(buffer);
        }
    }
}
'@

$path = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
$before = Get-ItemProperty $path
if ($Mode -eq 'Enable') {
    if ($before.DefaultUserName -and $before.DefaultUserName -ne $UserName) {
        throw 'An existing automatic-login account differs; explicit review is required.'
    }
    # Receive the credential over SSH stdin, not command arguments or a file.
    $inputData = [Console]::In.ReadLine() | ConvertFrom-Json
    if (-not ($inputData.password -is [string]) -or -not $inputData.password) {
        throw 'A nonempty password is required on standard input.'
    }
    $password = ConvertTo-SecureString $inputData.password -AsPlainText -Force
    $inputData.password = $null
    try {
        [LabCanvasAutologonSecret]::ValidateAndStore($UserName, $env:COMPUTERNAME, $password)
    } finally {
        $password.Dispose()
    }
    if (-not [LabCanvasAutologonSecret]::HasSecret()) {
        throw 'LSA secret verification failed; automatic login was not enabled.'
    }
    New-ItemProperty $path -Name DefaultUserName -Value $UserName -PropertyType String -Force | Out-Null
    New-ItemProperty $path -Name DefaultDomainName -Value $env:COMPUTERNAME -PropertyType String -Force | Out-Null
    Remove-ItemProperty $path -Name DefaultPassword -ErrorAction SilentlyContinue
    Remove-ItemProperty $path -Name AutoLogonCount -ErrorAction SilentlyContinue
    New-ItemProperty $path -Name AutoAdminLogon -Value '1' -PropertyType String -Force | Out-Null
} elseif ($Mode -eq 'Disable') {
    # Leave the encrypted secret intact; only disable automatic entry.
    New-ItemProperty $path -Name AutoAdminLogon -Value '0' -PropertyType String -Force | Out-Null
}

$state = Get-ItemProperty $path
[ordered]@{
    computer = $env:COMPUTERNAME
    username = $state.DefaultUserName
    domain = $state.DefaultDomainName
    automatic_login = ($state.AutoAdminLogon -eq '1')
    lsa_secret_present = [LabCanvasAutologonSecret]::HasSecret()
    plaintext_registry_password_present = ($null -ne $state.DefaultPassword)
    limited_logon_count_present = ($null -ne $state.AutoLogonCount)
    reboot_performed = $false
} | ConvertTo-Json -Compress
