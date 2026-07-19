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
- List every subscriber on an account.
- Update a domain's nameservers.
- Manage glue host records (create, update, delete, list, info).
- Read pending account notifications (poll queue).

## Installation
```bash
pip install .
```

### Shell completion (bash)
`hrd` uses Click, which provides bash completion out of the box (no extra dependency needed).
Add this to your `~/.bashrc`:
```bash
eval "$(_HRD_COMPLETE=bash_source hrd)"
```
Then reload your shell (`source ~/.bashrc` or open a new terminal). `hrd <TAB>` will complete
subcommands, and `hrd --profile <TAB>` etc. will complete options.

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
hrd history --limit 20            # recent operations across all profiles, with date and profile
hrd domain-info example.com       # full domain details, including the owner
hrd owner-info 173216             # subscriber details and every domain they own
hrd owner-list                    # every subscriber id on the account(s)
hrd owner-list --details          # ... plus each subscriber's name
hrd nameservers example.com ns1.example.com ns2.example.com  # update a domain's nameservers
hrd host list                     # list glue host records
hrd host info ns1.example.com     # show a glue host's IP addresses
hrd host create ns1.example.com --ipv4 1.2.3.4
hrd host update ns1.example.com --ipv4 1.2.3.5
hrd host delete ns1.example.com
hrd notifications                 # peek at the oldest pending account notification per profile
hrd notifications --ack --limit 10  # drain and acknowledge up to 10 notifications
hrd --debug balance               # print raw API requests/responses (password is masked)
```

### Library
```python
from hrd_py import HRDClient

client = HRDClient(login, password, api_hash)
client.login()
balance = client.get_balance()
print(f"Balance: {balance.balance}")
```
