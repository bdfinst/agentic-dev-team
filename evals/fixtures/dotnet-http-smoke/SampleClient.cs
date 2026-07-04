// Smoke fixture for issue #524 — a minimal outbound HTTP client that defines
// the "outbound HTTP code path" trigger from acceptance criterion A5: the
// constructor accepts HttpClient as a parameter. Not built. Not executed.
// Exists so /cd-test-architecture sees a real consumer-side seam and emits
// the test-stack-profiles/dotnet.md → references/csharp-http-client-testing.md
// citation chain.

using System.Net.Http;
using System.Threading.Tasks;

namespace StackAwareSmoke;

public sealed class SampleClient
{
    private readonly HttpClient _http;

    public SampleClient(HttpClient http)
    {
        _http = http;
    }

    public Task<HttpResponseMessage> GetAsync(string path)
        => _http.GetAsync(path);
}
