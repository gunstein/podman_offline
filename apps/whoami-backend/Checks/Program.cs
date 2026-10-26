using System.Security.Cryptography;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;

// Build-time check of the issuer pin (run by the Containerfile; a failure stops
// the image build). A correctly signed token whose issuer matches discovery but
// not the public origin must be rejected; the ASP.NET handler adds the discovery
// issuer to ValidIssuers, so this mimics that.
const string Public = "https://public.example:8443/identity";
const string Discovered = "http://identity-server:8080/identity";
var key = new RsaSecurityKey(RSA.Create(2048));
var handler = new JsonWebTokenHandler();
string Token(string issuer) => handler.CreateToken(new SecurityTokenDescriptor {
    Issuer = issuer, Audience = "app3", Expires = DateTime.UtcNow.AddMinutes(5),
    SigningCredentials = new SigningCredentials(key, SecurityAlgorithms.RsaSha256),
});
TokenValidationParameters Parameters(bool pinned) {
    var parameters = new TokenValidationParameters {
        ValidIssuer = Public, ValidIssuers = new[] { Discovered },
        ValidAudience = "app3", IssuerSigningKey = key,
    };
    if (pinned) parameters.IssuerValidator = (actual, _, _) => Oidc.PublicIssuer(Public, actual);
    return parameters;
}
async Task<bool> Valid(string issuer, bool pinned) =>
    (await handler.ValidateTokenAsync(Token(issuer), Parameters(pinned))).IsValid;

var results = new (string Name, bool Actual, bool Expected)[] {
    ("unpinned accepts the discovery issuer (the risk)", await Valid(Discovered, false), true),
    ("pinned rejects the discovery issuer", await Valid(Discovered, true), false),
    ("pinned accepts the public issuer", await Valid(Public, true), true),
};
foreach (var (name, actual, expected) in results)
    Console.WriteLine((actual == expected ? "PASS: " : "FAIL: ") + name);
return results.All(result => result.Actual == result.Expected) ? 0 : 1;
