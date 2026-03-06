import express, { Request, Response } from "express";

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ISSUE: Reflected XSS - user input directly in HTML response
app.get("/search", (req: Request, res: Response) => {
  const query = req.query.q as string;
  res.send(`
    <html>
      <head><title>Search Results</title></head>
      <body>
        <h1>Results for: ${query}</h1>
        <div id="results"></div>
      </body>
    </html>
  `);
});

// ISSUE: Stored XSS - innerHTML set with unsanitized user data
app.get("/api/comments/render", async (req: Request, res: Response) => {
  const comment = req.query.text as string;
  res.send(`
    <html>
      <body>
        <div id="comment"></div>
        <script>
          document.getElementById('comment').innerHTML = "${comment}";
        </script>
      </body>
    </html>
  `);
});

// ISSUE: DOM XSS via user-controlled URL parameter injected into script
app.get("/profile/:username", (req: Request, res: Response) => {
  const username = req.params.username;
  res.send(`
    <html>
      <body>
        <h1>Profile</h1>
        <script>
          var user = "${username}";
          document.write("<h2>Welcome, " + user + "</h2>");
        </script>
      </body>
    </html>
  `);
});

// ISSUE: No CSP header, no output encoding on error messages
app.use((err: Error, req: Request, res: Response, _next: unknown) => {
  res.status(500).send(`
    <html>
      <body>
        <h1>Error</h1>
        <p>${err.message}</p>
        <p>Request path: ${req.originalUrl}</p>
      </body>
    </html>
  `);
});

export default app;
