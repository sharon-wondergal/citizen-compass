"""Security headers sent with every response.

They tell browsers to refuse common attacks, even if a mistake elsewhere let
something unsafe into a page.
"""

# Scripts may only come from this site, so injected script tags and inline
# event handlers won't run. Inline styles are allowed because the progress bars
# and charts set their widths with style attributes, and styles can't run code.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])

HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    # Don't let other sites show this one inside a frame (clickjacking).
    "X-Frame-Options": "DENY",
    # Don't guess file types. A text file must never run as a script.
    "X-Content-Type-Options": "nosniff",
    # Share only the site's name, not the full address, when following links.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # The site never needs these, so refuse them.
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# Tells browsers to use HTTPS only, for a year. Only sent in production,
# because a local development server doesn't use HTTPS.
HSTS = "max-age=31536000; includeSubDomains"


def register_security_headers(app):
    @app.after_request
    def add_security_headers(response):
        for name, value in HEADERS.items():
            response.headers.setdefault(name, value)
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        return response
