# SENT-006 — Missing or ineffective route authentication

## Problem
An analyzed HTTP route lacks inherited authentication or uses a verifier that does not provide a recognized credential check and rejection path. The rule covers routes whose authentication is not established by the configured public-route list, application middleware, or dependency analysis.

## Impact
Requests may reach a route without the credential checks the application expects, allowing unauthorized actions or data access. The finding does not establish that a request bypassed authentication in a running service.

## Evidence
The AST rule `sentinel.sent006.route-authentication` examines Python functions decorated with `get`, `post`, `put`, `patch`, `delete`, `options`, `head`, or `api_route` calls whose route argument is a string literal. It exempts methods matching configured `public_routes`, a module containing `add_middleware(AuthenticationMiddleware)`, or route dependencies using `Depends`/`Security` that resolve to a function reading a token, credential, authorization, or session name, calling `jwt.decode`, `compare_digest`, or `.verify`, and raising an exception. Otherwise it records a `missing-auth` match at the decorator.

## Recommended action
Require credential verification and an explicit rejection path before route execution. Apply a trusted authentication middleware or dependency to every protected method, and keep the public-route configuration limited to intentionally public endpoints.

## How to verify
Run `pano scan <path>` again. The SENT-006 finding should be absent when each analyzed route is intentionally public under `public_routes`, inherits `AuthenticationMiddleware`, or has a recognized verifying dependency with a rejection path.

## Limits
This is static intraprocedural AST evidence, not an observation of HTTP requests or proof that unauthorized access succeeds. Only literal routes, the listed decorator methods, configured public patterns, direct middleware calls, and recognizable `Depends`/`Security` verifier bodies are analyzed; aliases, custom frameworks, indirect middleware, interprocedural checks, dynamic routes, and unscanned files may not be represented.
