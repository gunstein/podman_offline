using System.Security.Claims;
using System.Security.Cryptography.X509Certificates;
using System.Text.Encodings.Web;
using Duende.IdentityServer;
using Duende.IdentityServer.Models;
using Duende.IdentityServer.Services;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Identity;
using Npgsql;

var builder = WebApplication.CreateBuilder(args);
string Required(string key) => builder.Configuration[key]
    ?? throw new InvalidOperationException($"Missing {key}");
var origin = Required("PUBLIC_ORIGIN").TrimEnd('/');
var connectionString = new NpgsqlConnectionStringBuilder {
    Host = Required("DATABASE_HOST"), Database = "identity", Username = "identity",
    Password = File.ReadAllText("/run/secrets/database/password").Trim(), Timeout = 5
}.ConnectionString;
var source = NpgsqlDataSource.Create(connectionString);
builder.Services.AddSingleton(source);
builder.Services.AddAntiforgery();
builder.Services.AddDataProtection()
    .PersistKeysToFileSystem(new DirectoryInfo("/data/protection"));
builder.Services.Configure<ForwardedHeadersOptions>(options => {
    options.ForwardedHeaders = ForwardedHeaders.XForwardedProto | ForwardedHeaders.XForwardedHost;
    // Only nginx publishes a host port; all other pods are on the private network.
    options.KnownNetworks.Clear();
    options.KnownProxies.Clear();
});
var signing = X509Certificate2.CreateFromPemFile(
    "/run/secrets/signing/identity.crt", "/run/secrets/signing/identity.key");
var clientCertificate = X509Certificate2.CreateFromPem(File.ReadAllText("/run/secrets/client/todo-client.crt"));
builder.Services.AddIdentityServer(options => {
    options.IssuerUri = origin + "/identity";
    options.KeyManagement.Enabled = false;
    options.UserInteraction.LoginUrl = "/account/login";
})
    .AddSigningCredential(signing)
    .AddInMemoryIdentityResources(new IdentityResource[] {
        new IdentityResources.OpenId(), new IdentityResources.Profile()
    })
    .AddInMemoryApiScopes(new[] { new ApiScope("todo") })
    .AddInMemoryClients(new[] { new Client {
        ClientId = "todo", ClientName = "Todo", AllowedGrantTypes = GrantTypes.Code,
        RequirePkce = true, RequireConsent = false,
        RedirectUris = { origin + "/auth/callback" },
        AllowedScopes = { "openid", "profile", "todo" },
        ClientSecrets = { new Duende.IdentityServer.Models.Secret {
            Type = IdentityServerConstants.SecretTypes.X509CertificateBase64,
            Value = Convert.ToBase64String(clientCertificate.RawData)
        }}
    }})
    .AddJwtBearerClientAuthentication();

var app = builder.Build();
var hasher = new PasswordHasher<string>();
// Small demo user store; password hashes persist in the identity database.
for (var attempt = 0; ; attempt++) {
    try {
        await using var connection = await source.OpenConnectionAsync();
        await using var create = new NpgsqlCommand(
            "CREATE TABLE IF NOT EXISTS users (username text PRIMARY KEY, password_hash text NOT NULL)", connection);
        await create.ExecuteNonQueryAsync();
        foreach (var username in new[] { "alice", "bob" }) {
            var password = File.ReadAllText("/run/secrets/users/" + username + "-password").Trim();
            await using var insert = new NpgsqlCommand(
                "INSERT INTO users VALUES ($1, $2) ON CONFLICT DO NOTHING", connection);
            insert.Parameters.AddWithValue(username);
            insert.Parameters.AddWithValue(hasher.HashPassword(username, password));
            await insert.ExecuteNonQueryAsync();
        }
        break;
    } catch (NpgsqlException) when (attempt < 59) { await Task.Delay(1000); }
}
app.UseForwardedHeaders();
app.UsePathBase("/identity");
app.UseIdentityServer();
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
app.MapGet("/account/login", (HttpContext context, IAntiforgery antiforgery,
    IIdentityServerInteractionService interaction) => {
    var returnUrl = context.Request.Query["returnUrl"].ToString();
    if (!interaction.IsValidReturnUrl(returnUrl)) return Results.BadRequest("Invalid return URL");
    var tokens = antiforgery.GetAndStoreTokens(context);
    string Escape(string? value) => HtmlEncoder.Default.Encode(value ?? "");
    var html = "<!doctype html><html lang=nb><meta charset=utf-8><title>Logg inn</title>" +
        "<h1>Duende – logg inn</h1><form method=post>" +
        "<input type=hidden name=returnUrl value=\"" + Escape(returnUrl) + "\">" +
        "<input type=hidden name=\"" + Escape(tokens.FormFieldName) + "\" value=\"" +
        Escape(tokens.RequestToken) + "\">" +
        "<p><label>Brukernavn <input name=username autocomplete=username required></label></p>" +
        "<p><label>Passord <input name=password type=password autocomplete=current-password required></label></p>" +
        "<button>Logg inn</button></form></html>";
    return Results.Content(html, "text/html; charset=utf-8");
});
app.MapPost("/account/login", async (HttpContext context, IAntiforgery antiforgery,
    IIdentityServerInteractionService interaction) => {
    try { await antiforgery.ValidateRequestAsync(context); }
    catch (AntiforgeryValidationException) { return Results.BadRequest("Invalid form token"); }
    var form = await context.Request.ReadFormAsync();
    var returnUrl = form["returnUrl"].ToString();
    if (!interaction.IsValidReturnUrl(returnUrl)) return Results.BadRequest("Invalid return URL");
    var username = form["username"].ToString();
    await using var command = source.CreateCommand("SELECT password_hash FROM users WHERE username = $1");
    command.Parameters.AddWithValue(username);
    var hash = await command.ExecuteScalarAsync() as string;
    if (hash is null || hasher.VerifyHashedPassword(username, hash, form["password"].ToString())
        == PasswordVerificationResult.Failed) return Results.Unauthorized();
    await context.SignInAsync(new IdentityServerUser(username) {
        DisplayName = username, AdditionalClaims = new[] { new Claim("name", username) }
    }, new AuthenticationProperties { IsPersistent = false });
    return Results.Redirect(returnUrl);
});
app.Run();
