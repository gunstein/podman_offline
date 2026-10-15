using System.Globalization;
using System.Text;
using Npgsql;

// In-image startup: compose once before ASP.NET reads its environment provider.
// The application below consumes only ConnectionStrings__Default, never a fallback.
internal static class DatabaseEnvironment
{
    public static void Initialize()
    {
        string Required(string key)
        {
            var value = Environment.GetEnvironmentVariable(key);
            if (string.IsNullOrEmpty(value) || value.Contains('\0'))
                throw new InvalidOperationException($"Missing or invalid {key}");
            return value;
        }
        var host = Required("DB_HOST");
        var portText = Required("DB_PORT");
        var user = Required("DB_USER");
        var database = Required("DB_NAME");
        if (portText.Length > 5 || !portText.All(c => c >= '0' && c <= '9') ||
            !int.TryParse(portText, NumberStyles.None, CultureInfo.InvariantCulture, out var port) ||
            port < 1 || port > 65535)
            throw new InvalidOperationException("Invalid DB_PORT (expected 1-65535)");
        string password;
        try
        {
            // Match postgres file_env's command substitution: strip trailing LF only.
            password = new UTF8Encoding(false, true).GetString(
                File.ReadAllBytes("/run/secrets/database/password")).TrimEnd('\n');
        }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException || error is DecoderFallbackException)
        {
            throw new InvalidOperationException("Cannot read database password file");
        }
        if (password.Length == 0 || password.IndexOfAny(new[] { '\0', '\r', '\n' }) >= 0)
            throw new InvalidOperationException("Empty or invalid database password file");
        try
        {
            Environment.SetEnvironmentVariable("ConnectionStrings__Default",
                new NpgsqlConnectionStringBuilder {
                    Host = host, Port = port, Username = user, Database = database,
                    Password = password, Timeout = 5, IncludeErrorDetail = false
                }.ConnectionString);
        }
        catch (ArgumentException)
        {
            throw new InvalidOperationException("Invalid database parameters");
        }
    }
}
