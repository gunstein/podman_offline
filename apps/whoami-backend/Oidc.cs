using Microsoft.IdentityModel.Tokens;

// OIDC rules kept apart from Program.cs so Checks/ can verify them at build time.
public static class Oidc {
    // ASP.NET adds the discovery document's issuer to the valid issuers; with the
    // internal discovery address that would be a second, unchecked issuer.
    public static string PublicIssuer(string expected, string actual) =>
        actual == expected
            ? actual
            : throw new SecurityTokenInvalidIssuerException("Token issuer is not the public issuer");
}
