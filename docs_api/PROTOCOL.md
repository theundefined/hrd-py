# HRD.pl API Protocol Documentation

This document describes the low-level communication protocol for the HRD.pl API (port 9999), based on reverse-engineering the official PHP library and empirical testing.

## Connection
- **Host:** `api.hrd.pl`
- **Port:** `9999`
- **Security:** SSL/TLS (TLS 1.2+ recommended).
- **Framing:** Every message (request and response) is prefixed with a **4-byte big-endian unsigned integer** representing the length of the following payload.

## Request Structure
A request payload consists of two parts:
1. **Signature (64 bytes):** A binary SHA512 hash.
2. **XML Payload:** The actual command in XML format.

### Hashing / Signing
The signature is calculated as:
`SHA512(XML_Payload + binary_api_hash)`

- `XML_Payload`: The UTF-8 encoded XML string.
- `binary_api_hash`: The API hash provided by HRD.pl, converted from hex string to binary bytes.

### XML Format
- **Root Element:** `<api xmlns="http://api.hrd.pl/api/">`
- **Namespace:** The namespace `http://api.hrd.pl/api/` is mandatory for the root element.
- **Session Management:**
    - The `login` command returns a `<token>`.
    - **CRITICAL:** Unlike many other APIs, this token is **NOT** included in the XML body of subsequent requests.
    - Authentication for subsequent requests is handled solely by the **Signature** (which uses the API hash).
    - The token is only used for "session restoration" via `loginByToken` if implemented.

## Response Structure
- Prefixed with 4-byte length.
- The payload is a raw XML string.
- The root `<api>` element often contains a `<status>` tag (`ok` or `error`) and a `<message>` tag on error.

## Common Data Formats
- **Dates:** Usually returned in `YYYY-MM-DD HH:MM:SS` or `YYYY-MM-DD`.
- **Domain Names:** Should be converted to ASCII (Punycode) before being sent if they contain non-ASCII characters.

## Known Modules
- `login`: Initial authentication.
- `partner`: Account balance, pricings, etc.
- `domain`: Registration, info, renewal, listing.
- `poll`: Message queue for event notifications.
