using System.Security.Claims;
using System.Security.Cryptography.X509Certificates;
using System.Text.Encodings.Web;
using System.Text.Json;
using Duende.IdentityServer;
using Duende.IdentityServer.Models;
using Duende.IdentityServer.Services;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Identity;
using Npgsql;

// The complete connection string is supplied by configuration, also in unchanged images.
var connectionString = Environment.GetEnvironmentVariable("ConnectionStrings__Default");
if (string.IsNullOrWhiteSpace(connectionString)) {
    Console.Error.WriteLine("Missing ConnectionStrings__Default");
    return 1;
}
NpgsqlDataSource source;
try { source = NpgsqlDataSource.Create(connectionString); }
catch (ArgumentException) {
    Console.Error.WriteLine("Invalid ConnectionStrings__Default");
    return 1;
}
// Focused container verification uses the exact same startup and environment path.
if (args.Contains("--database-check")) {
    try {
        await using var connection = await source.OpenConnectionAsync();
        await using var command = new NpgsqlCommand("SELECT 1", connection);
        await command.ExecuteScalarAsync();
        Console.WriteLine("Database connection verified via ConnectionStrings__Default");
        return 0;
    } catch (PostgresException error) when (error.SqlState == "28P01") {
        Console.Error.WriteLine("Database authentication failed (28P01); restore matching credentials; no password changed");
        return 2;
    } catch (NpgsqlException) {
        Console.Error.WriteLine("Database connection failed");
        return 3;
    }
}
var builder = WebApplication.CreateBuilder(args);
string Required(string key) => builder.Configuration[key]
    ?? throw new InvalidOperationException($"Missing {key}");
var origin = Required("PUBLIC_ORIGIN").TrimEnd('/');
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
// Client registrations contain only public certificates; new imports take effect on restart.
var registrations = JsonSerializer.Deserialize<string[]>(File.ReadAllText("/clients/installed.json"))
    ?? throw new InvalidOperationException("Missing client index");
var clients = registrations.Select(path => LoadClient(Path.Combine("/clients", path))).ToArray();
if (clients.Select(client => client.ClientId).Distinct().Count() != clients.Length)
    throw new InvalidOperationException("Duplicate OIDC client IDs");
// API resources (backlog 77): names and scopes from ENVIRONMENT; each secret
// is the API's raw value from the platform-rendered identity-apis Secret
// (the API's own secret, named on the ApiSecrets line). A named
// API without a secret is not installed yet and stays inactive.
var configuredApis = builder.Configuration.GetSection("ApiResources").Get<ApiResource[]>()
    ?? Array.Empty<ApiResource>();
if (configuredApis.Any(api => string.IsNullOrEmpty(api.Name) || api.ApiSecrets.Count > 1))
    throw new InvalidOperationException("Each API resource needs a name and at most one secret");
var apiResources = configuredApis.Where(api => api.ApiSecrets.Count == 1).ToArray();
foreach (var api in configuredApis.Except(apiResources))
    Console.WriteLine($"API resource {api.Name} has no registered secret; inactive");
// Duende compares Base64(SHA-256) of the presented secret: hash each raw value
// once, in memory only. An empty value is a delivery error; never print it.
foreach (var secret in apiResources.Select(api => (api, secret: api.ApiSecrets.Single())))
{
    if (string.IsNullOrWhiteSpace(secret.secret.Value))
        throw new InvalidOperationException($"API resource {secret.api.Name} has an empty secret");
    secret.secret.Value = secret.secret.Value.Sha256();
}
builder.Services.AddIdentityServer(options => {
    options.IssuerUri = origin + "/identity";
    options.KeyManagement.Enabled = false;
    options.UserInteraction.LoginUrl = "/account/login";
})
    .AddSigningCredential(signing)
    .AddInMemoryIdentityResources(new IdentityResource[] {
        new IdentityResources.OpenId(), new IdentityResources.Profile()
    })
    .AddInMemoryApiScopes(clients.SelectMany(client => client.AllowedScopes)
        .Where(scope => scope != "openid" && scope != "profile").Distinct()
        .Select(scope => new ApiScope(scope)))
    .AddInMemoryApiResources(apiResources)
    .AddInMemoryClients(clients)
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
    } catch (PostgresException error) when (error.SqlState == "28P01") {
        Console.Error.WriteLine("Database authentication failed (28P01); restore matching credentials; no password changed");
        return 2;
    } catch (NpgsqlException) {
        if (attempt == 59) {
            Console.Error.WriteLine("Database connection failed during startup");
            return 3;
        }
        await Task.Delay(1000);
    }
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
    var html = "<!doctype html><html lang=en><meta charset=utf-8><title>Sign in</title>" +
        "<h1>Duende – sign in</h1><form method=post>" +
        "<input type=hidden name=returnUrl value=\"" + Escape(returnUrl) + "\">" +
        "<input type=hidden name=\"" + Escape(tokens.FormFieldName) + "\" value=\"" +
        Escape(tokens.RequestToken) + "\">" +
        "<p><label>User name <input name=username autocomplete=username required></label></p>" +
        "<p><label>Password <input name=password type=password autocomplete=current-password required></label></p>" +
        "<button>Sign in</button></form></html>";
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
return 0;

// Load one validated public client registration and its adjacent certificate.
static Client LoadClient(string path) {
    var config = JsonSerializer.Deserialize<ClientConfig>(File.ReadAllText(path))
        ?? throw new InvalidOperationException("Missing client registration");
    if (config.Certificate != "client.crt") throw new InvalidOperationException("Invalid certificate filename");
    var certificate = X509Certificate2.CreateFromPem(File.ReadAllText(Path.Combine(Path.GetDirectoryName(path)!, config.Certificate)));
    return new Client {
        ClientId = config.Id, ClientName = config.Id, AllowedGrantTypes = GrantTypes.Code,
        RequirePkce = true, RequireConsent = false,
        RedirectUris = config.RedirectUris, AllowedScopes = config.Scopes,
        ClientSecrets = { new Duende.IdentityServer.Models.Secret {
            Type = IdentityServerConstants.SecretTypes.X509CertificateBase64,
            Value = Convert.ToBase64String(certificate.RawData)
        }}
    };
}

// Public registration data loaded from the imported clients volume.
sealed record ClientConfig(string Id, string[] RedirectUris, string[] Scopes, string Certificate);
