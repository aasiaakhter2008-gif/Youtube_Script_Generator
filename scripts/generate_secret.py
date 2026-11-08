import hashlib
import hmac
import logging
import secrets
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generate-secret")

# The exact hardcoded value that must never be used in production.
BANNED_DEFAULT = "dev-insecure-key-change-me"


def main() -> None:
    key = secrets.token_urlsafe(48)
    print(key)
    logger.info("Generated a %d-character API key. Set it via the API_KEY environment variable.", len(key))
    logger.info("For WebAuth use a different secret per environment and keep it out of git.")
    sys.exit(0)


if __name__ == "__main__":
    main()
