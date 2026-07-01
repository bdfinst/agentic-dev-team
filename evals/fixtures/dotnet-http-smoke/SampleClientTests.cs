// Smoke fixture for issue #524 — a deliberate Mock<HttpClient> smell, exactly
// the anti-pattern catalogued at knowledge/references/csharp-http-client-testing.md
// ("Common smells in C# HTTP-consumer tests" — "Mocking HttpClient directly").
// Exists so /test-smell-review produces a finding citing that reference. Not
// built. Not executed.

using Moq;
using System.Net.Http;
using Xunit;

namespace StackAwareSmoke;

public class SampleClientTests
{
    [Fact]
    public void Constructs_with_a_mocked_HttpClient()
    {
        // Smell: mocking HttpClient directly. The seam should be a stubbed
        // HttpMessageHandler wrapped by an owned adapter — see
        // knowledge/references/csharp-http-client-testing.md.
        var mock = new Mock<HttpClient>();
        var client = new SampleClient(mock.Object);
        Assert.NotNull(client);
    }
}
