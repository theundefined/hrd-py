# hrd-py

A Python library and CLI for the HRD.pl API.

## Features
- Check account balance.
- List domains and their status.
- Monitor domain expiry.
- Renew domains manually or automatically.
- View account operation history (purchases, renewals, etc.).
- Show full domain details, including the registrant/owner.
- Look up a subscriber (abonent) and every domain they own.

## Installation
```bash
pip install .
```

## Configuration
Create a `.env` file with your HRD.pl credentials:
```env
HRD_LOGIN=your_login
HRD_PASS=your_api_password
HRD_HASH=your_api_hash
```

## Usage
### CLI
```bash
hrd balance
hrd domains --all
hrd expiring --days 30
hrd renew example.com
hrd auto-renew --days 7           # asks before renewing each domain, across all profiles
hrd auto-renew --days 7 --no-ask  # renew without confirmation prompts
hrd history --limit 20            # recent operations across all profiles, with date and owner
hrd domain-info example.com       # full domain details, including the owner
hrd owner-info 173216             # subscriber details and every domain they own
hrd --debug balance               # print raw API requests/responses (includes credentials!)
```

### Library
```python
from hrd_py import HRDClient

client = HRDClient(login, password, api_hash)
client.login()
balance = client.get_balance()
print(f"Balance: {balance.balance}")
```
