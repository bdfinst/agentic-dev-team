using System;
using System.Linq;
using System.Threading.Tasks;
using Xunit;

// Fixture for xunit_v3_feature_detector — exercises each shim-breaking v3-only
// construct PLUS near-miss negatives that must NOT be flagged. See #1160.
public class V3FeaturesTests : IAsyncLifetime
{
    [Fact(Explicit = true)]
    public void ExplicitFact()
    {
        Assert.True(true);
    }

    [Theory(Explicit = true)]
    [InlineData(1)]
    public void ExplicitTheory(int x)
    {
        Assert.Equal(1, x);
    }

    [Fact]
    public void DynamicSkip()
    {
        Assert.SkipWhen(DateTime.Now.Hour < 0, "never");
        Assert.Skip("bare skip");
        Assert.SkipUnless(true, "unless");
        Assert.Equal(4, 2 + 2);
    }

    [Fact]
    public void UsesTestContext()
    {
        var name = TestContext.Current.Test.TestDisplayName;
        Assert.NotNull(name);
    }

    public static TheoryDataRow<int> RowData() => new(1);

    public ValueTask InitializeAsync() => ValueTask.CompletedTask;

    public ValueTask DisposeAsync() => ValueTask.CompletedTask;

    // --- Near-miss negatives: none of these must be flagged ---

    // [Fact(Explicit = true)]  <- commented-out attribute, must be ignored

    [Fact(Explicit = false)]
    public void NotActuallyExplicit()
    {
        Assert.Equal(2, 1 + 1);
    }

    [Fact]
    public void PlainV2CompatibleTest()
    {
        var tail = new[] { 1, 2, 3 }.Skip(1).ToArray(); // LINQ .Skip, not Assert.Skip
        Assert.Equal(2, tail.Length);
    }
}
