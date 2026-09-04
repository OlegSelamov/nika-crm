# Gunicorn runtime configuration for Nika Business.
# AI requests can legitimately take longer than the default 30 seconds,
# especially when the OpenAI client retries temporary network/API errors.

timeout = 180
graceful_timeout = 30
keepalive = 5
