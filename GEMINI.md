# Project: hrd-py

## Core Mandates
- **API Protocol:** This library communicates with the HRD.pl API on port 9999 using a custom SSL/TLS based protocol. See [docs_api/PROTOCOL.md](docs_api/PROTOCOL.md) for full details.
- **Authentication:** All requests MUST be signed using `SHA512(XML_Payload + binary_api_hash)`. The session token returned by `login` is NOT sent back in subsequent requests.
- **Data Parsing:** Dates from the API can include time (`%Y-%m-%d %H:%M:%S`). Ensure robust parsing to avoid "Unknown" values.
- **CLI Consistency:** Use `load_dotenv(override=True)` to ensure `.env` file credentials take precedence.

## Development Status
- **Implemented:** Balance fetching, domain listing, domain info.
- **Reference:** The official PHP library is cloned in `docs_api/php-lib` for reference. Use it to verify method implementations.
