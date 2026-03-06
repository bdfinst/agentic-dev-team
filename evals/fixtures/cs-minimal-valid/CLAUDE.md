# url-shortener

A simple URL shortener service built with Go and SQLite.

## Overview

Accepts long URLs via a REST API and returns shortened links. Redirects short links to the original URL. Tracks click counts per link.

## Project Structure

- `main.go` — Entry point and HTTP server setup
- `handlers/` — Route handlers for create, redirect, and stats
- `store/` — SQLite persistence layer
- `migrations/` — SQL migration files

## Commands

- `go run .` — Start the server on port 8080
- `go test ./...` — Run all tests
- `go build -o shortener .` — Build the binary
- `curl -X POST localhost:8080/shorten -d '{"url":"https://example.com"}'` — Create a short link

## Notes

- No authentication required; this is an internal tool.
- Rate limiting is handled upstream by the load balancer.
