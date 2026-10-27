using System.Security.Cryptography.X509Certificates;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;

// Small "whoami" BFF: OIDC tokens stay on the server; the browser gets a cookie.
var builder = WebApplication.CreateBuilder(args);
string Required(string key) => builder.Configuration[key] is { Length: > 0 } value
    ? value : throw new InvalidOperationException($"Missing {key}");
var origin = Required("PUBLIC_ORIGIN").TrimEnd('/');
var appId = Required("APP_ID");
var basePath = Required("BASE_PATH").TrimEnd('/');
var issuer = origin + "/identity";
// Optional internal variant (backlog 71 b): discovery, keys and token over the
// Podman network; the issuer and the browser's endpoints stay public.
var internalIdentity = builder.Configuration["IDENTITY_INTERNAL_URL"]?.TrimEnd('/');
if (string.IsNullOrEmpty(internalIdentity)) internalIdentity = null;
var clientCertificate = X509Certificate2.CreateFromPemFile(
    "/run/secrets/client/client.crt", "/run/secrets/client/client.key");
// The handler logs Identity's error_description and error_uri verbatim; those
// are supplied by the protocol peer, so OnRemoteFailure logs a fixed line instead.
builder.Logging.AddFilter("Microsoft.AspNetCore.Authentication.OpenIdConnect", LogLevel.None);

// Keys protect sign-in cookies and antiforgery tokens; a volume keeps them across restarts.
builder.Services.AddDataProtection()
    .SetApplicationName(appId)
    .PersistKeysToFileSystem(new DirectoryInfo("/data/protection"));
builder.Services.Configure<ForwardedHeadersOptions>(options => {
    // nginx sets X-Forwarded-Proto; without it redirect URIs would use http.
    options.ForwardedHeaders = ForwardedHeaders.XForwardedProto;
    // Only nginx publishes a host port; all other pods are on the private network.
    options.KnownNetworks.Clear();
    options.KnownProxies.Clear();
});
builder.Services.AddAntiforgery(options => {
    options.HeaderName = "X-CSRF-Token";
    options.Cookie.Name = appId + "-csrf";
    options.Cookie.Path = basePath + "/";
    options.Cookie.SecurePolicy = CookieSecurePolicy.Always;
});
builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
    .AddCookie(options => {
        options.Cookie.Name = appId + "-session";
        options.Cookie.Path = basePath + "/";
        options.Cookie.HttpOnly = true;
        options.Cookie.SecurePolicy = CookieSecurePolicy.Always;
        options.Cookie.SameSite = SameSiteMode.Lax;
        options.ExpireTimeSpan = TimeSpan.FromHours(1);
        options.SlidingExpiration = false;
        // The API answers 401/403; only /auth/login starts a sign-in.
        options.Events.OnRedirectToLogin = context => {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            return Task.CompletedTask;
        };
        options.Events.OnRedirectToAccessDenied = context => {
            context.Response.StatusCode = StatusCodes.Status403Forbidden;
            return Task.CompletedTask;
        };
    })
    .AddOpenIdConnect(options => {
        options.Authority = issuer;
        options.ClientId = appId;
        options.ResponseType = "code";
        options.UsePkce = true;
        // The client protocol's redirect URI is origin + BASE_PATH + /auth/callback;
        // UsePathBase below supplies BASE_PATH.
        options.CallbackPath = "/auth/callback";
        options.Scope.Clear();
        foreach (var scope in new[] { "openid", "profile", appId }) options.Scope.Add(scope);
        options.MapInboundClaims = false;
        options.GetClaimsFromUserInfoEndpoint = true;
        options.SaveTokens = false;
        options.TokenValidationParameters.NameClaimType = "name";
        // ASP.NET also accepts the issuer named by discovery; pin the public one.
        options.TokenValidationParameters.IssuerValidator =
            (actual, _, _) => Oidc.PublicIssuer(issuer, actual);
        if (internalIdentity is not null) {
            options.MetadataAddress = internalIdentity + "/.well-known/openid-configuration";
            options.RequireHttpsMetadata = false;
        }
        options.Events.OnRedirectToIdentityProvider = context => {
            // Duende builds discovery endpoints from the request's host, so an
            // internal document names the internal host; the browser needs the public one.
            if (internalIdentity is not null)
                context.ProtocolMessage.IssuerAddress = issuer + "/connect/authorize";
            return Task.CompletedTask;
        };
        options.Events.OnAuthorizationCodeReceived = async context => {
            // private_key_jwt: sign a short assertion with the registered client key.
            var configuration = await context.Options.ConfigurationManager!
                .GetConfigurationAsync(context.HttpContext.RequestAborted);
            context.TokenEndpointRequest!.ClientAssertionType =
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer";
            context.TokenEndpointRequest.ClientAssertion =
                ClientAssertion(appId, configuration.TokenEndpoint, clientCertificate);
        };
        options.Events.OnRemoteFailure = async context => {
            // Only the exception type and the request's trace ID: messages can carry
            // the peer's error_description, error_uri or token details.
            context.HttpContext.RequestServices.GetRequiredService<ILogger<Program>>().LogWarning(
                "OIDC sign-in failed: {Type} (trace {TraceId})",
                context.Failure?.GetType().Name, context.HttpContext.TraceIdentifier);
            context.Response.StatusCode = StatusCodes.Status400BadRequest;
            await context.Response.WriteAsync("Sign-in failed. Go back and try again.");
            context.HandleResponse();
        };
    });
builder.Services.AddAuthorization();

var app = builder.Build();
app.Logger.LogInformation(internalIdentity is null
    ? "Identity metadata through the public origin {Issuer}"
    : "Identity metadata through the internal address {Internal}; issuer stays {Issuer}",
    internalIdentity is null ? issuer : internalIdentity, issuer);
app.UseForwardedHeaders();
app.UsePathBase(basePath);
app.Use(async (context, next) => {
    // Prevent caching and MIME sniffing of backend responses.
    context.Response.Headers.CacheControl = "no-store";
    context.Response.Headers.XContentTypeOptions = "nosniff";
    await next();
});
app.UseAuthentication();
app.UseAuthorization();

// Liveness answers locally, without Identity or sign-in.
app.MapGet("/livez", () => Results.NoContent());
app.MapGet("/auth/login", () => Results.Challenge(
    new AuthenticationProperties { RedirectUri = basePath + "/" },
    new[] { OpenIdConnectDefaults.AuthenticationScheme }));
app.MapGet("/auth/me", (HttpContext context, IAntiforgery antiforgery) => {
    if (context.User.Identity?.IsAuthenticated != true)
        return Results.Ok(new { user = (object?)null, csrf = "" });
    var tokens = antiforgery.GetAndStoreTokens(context);
    var sub = context.User.FindFirst("sub")?.Value;
    return Results.Ok(new {
        user = new { sub, name = context.User.Identity.Name ?? sub }, csrf = tokens.RequestToken
    });
});
app.MapPost("/auth/logout", async (HttpContext context, IAntiforgery antiforgery) => {
    // Clear only this app's local session, after CSRF and origin checks.
    if (context.Request.Headers.Origin != origin) return Results.StatusCode(403);
    try { await antiforgery.ValidateRequestAsync(context); }
    catch (AntiforgeryValidationException) { return Results.StatusCode(403); }
    await context.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
    return Results.NoContent();
}).RequireAuthorization();
app.MapGet("/api/claims", (HttpContext context) => Results.Ok(
    context.User.Claims.Select(claim => new { type = claim.Type, value = claim.Value })))
    .RequireAuthorization();
app.Run();

// RFC 7523 client assertion for the token endpoint the request is sent to.
static string ClientAssertion(string clientId, string audience, X509Certificate2 certificate) {
    var now = DateTime.UtcNow;
    return new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor {
        Issuer = clientId,
        Audience = audience,
        IssuedAt = now,
        NotBefore = now,
        Expires = now.AddMinutes(1),
        Claims = new Dictionary<string, object> {
            ["sub"] = clientId, ["jti"] = Guid.NewGuid().ToString("N")
        },
        SigningCredentials = new X509SigningCredentials(certificate, SecurityAlgorithms.RsaSha256),
    });
}
