// Test fixture for the joern C# CPG path (issue #60).
//
// Deliberately vulnerable: HTTP query input flows unsanitized through a
// string concatenation into a SQL command (source -> string-concat -> sink).
// Consumed by:
//   - scripts/verify-joern-csharp.sh  (install-time C# frontend verification)
//   - skills/false-positive-reduction/tools/reachability.sh  (csharp detection)
// The chain is intentionally simple so a correctly-wired joern C# frontend
// produces a non-empty CPG with a traceable source->sink path.
using System.Data.SqlClient;
using Microsoft.AspNetCore.Mvc;

namespace Fixtures.JoernDotnet
{
    [ApiController]
    [Route("api/users")]
    public class VulnerableController : ControllerBase
    {
        private readonly string _connectionString;

        public VulnerableController(string connectionString)
        {
            _connectionString = connectionString;
        }

        [HttpGet]
        public IActionResult GetByName([FromQuery] string name)
        {
            // SINK: user-controlled 'name' concatenated straight into SQL text.
            var query = "SELECT * FROM Users WHERE Name = '" + name + "'";
            using var connection = new SqlConnection(_connectionString);
            using var command = new SqlCommand(query, connection);
            connection.Open();
            using var reader = command.ExecuteReader();
            return Ok(reader);
        }
    }
}
