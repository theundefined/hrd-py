import os
import sys
from datetime import datetime
from typing import Optional
import click
from .client import HRDClient
from .exceptions import HRDError
from .config import ConfigManager
from dotenv import load_dotenv

# Still load dotenv for backward compatibility or explicit override
load_dotenv(override=True)


class CLIContext:
    def __init__(self, profile=None, debug=False):
        self.config_manager = ConfigManager()
        self.explicit_profile = profile
        self.profile_name = profile or self.config_manager.get_default_profile_name()
        self.debug = debug
        self._client = None

    def get_client(self):
        if self._client:
            return self._client

        # 1. Try from config
        profile = self.config_manager.get_profile(self.profile_name)
        if profile:
            self._client = HRDClient(profile["login"], profile["password"], profile["api_hash"], debug=self.debug)
            return self._client

        # 2. Fallback to ENV (only if no specific profile requested)
        if not self.profile_name or self.profile_name == self.config_manager.get_default_profile_name():
            login = os.getenv("HRD_LOGIN")
            password = os.getenv("HRD_PASS")
            api_hash = os.getenv("HRD_HASH")

            if all([login, password, api_hash]):
                self._client = HRDClient(login, password, api_hash, debug=self.debug)
                return self._client

        click.echo(f"Error: Missing configuration for profile '{self.profile_name or 'default'}'.")
        click.echo("Use 'hrd profile add' to set up credentials.")
        sys.exit(1)

    def get_profiles_to_process(self):
        """Profiles to iterate for multi-profile commands: the pinned one, or all configured."""
        if self.explicit_profile:
            return [self.explicit_profile]

        profiles = self.config_manager.list_profiles()
        if not profiles and os.getenv("HRD_LOGIN"):
            profiles = [None]  # Use default/env logic
        return profiles


@click.group()
@click.option("--profile", help="Use a specific profile from config")
@click.option("--debug", is_flag=True, help="Show full API requests and responses")
@click.pass_context
def cli(ctx, profile, debug):
    """HRD.pl API Command Line Interface"""
    ctx.obj = CLIContext(profile, debug=debug)


@cli.group()
def profile():
    """Manage account profiles"""
    pass


@profile.command(name="add")
@click.argument("name")
@click.option("--login", prompt=True, help="HRD API Login")
@click.option("--password", prompt=True, hide_input=True, help="HRD API Password")
@click.option("--hash", prompt=True, help="HRD API Hash")
@click.pass_obj
def profile_add(obj, name, login, password, hash):
    """Add a new profile"""
    obj.config_manager.add_profile(name, login, password, hash)
    click.echo(f"Profile '{name}' added successfully.")


@profile.command(name="list")
@click.pass_obj
def profile_list(obj):
    """List all configured profiles"""
    profiles = obj.config_manager.list_profiles()
    default = obj.config_manager.get_default_profile_name()
    if not profiles:
        click.echo("No profiles configured.")
        return
    for p in profiles:
        star = "*" if p == default else " "
        click.echo(f"{star} {p}")


@profile.command(name="set-default")
@click.argument("name")
@click.pass_obj
def profile_set_default(obj, name):
    """Set a profile as default"""
    if obj.config_manager.set_default(name):
        click.echo(f"Default profile set to '{name}'.")
    else:
        click.echo(f"Error: Profile '{name}' not found.")


@cli.command()
@click.pass_obj
def balance(obj):
    """Show account balance.

    Shows the balance for every configured profile by default. Pass a
    specific profile with the global --profile option to restrict it to
    just that one.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            b = client.get_balance()
            click.echo(f"Profile: {p_name or 'default'}")
            click.echo(f"Current Balance: {b.balance}")
            click.echo(f"Restricted Balance: {b.restricted_balance}")
        except HRDError as e:
            click.echo(f"Error processing profile {p_name or 'default'}: {e}")


@cli.command()
@click.option("--all", is_flag=True, help="List all domains, not just expiring")
@click.option("--days", default=30, help="Days until expiry for filtering")
@click.pass_obj
def domains(obj, all, days):
    """List domains and their status.

    Fetches domains for every configured profile by default. Pass a
    specific profile with the global --profile option to restrict it to
    just that one.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        click.echo(f"\n--- Profile: {p_name or 'default'} ---")
        try:
            client = ctx_profile.get_client()
            client.login()
            domain_list = client.list_domains()

            shown = False
            for d in domain_list:
                if all or d.is_expiring_soon(days):
                    expiry_str = d.expiry_date.strftime("%Y-%m-%d") if d.expiry_date else "Unknown"
                    status_str = click.style(d.status, fg="red" if d.status == "expired" else "green")
                    click.echo(f"{d.name:30} | {expiry_str:10} | {status_str}")
                    shown = True

            if not shown:
                click.echo("No domains found.")
        except HRDError as e:
            click.echo(f"Error processing profile {p_name or 'default'}: {e}")


@cli.command(name="domain-info")
@click.argument("domain")
@click.pass_obj
def domain_info(obj, domain):
    """Show all available information about a domain, including its owner.

    Searches every configured profile by default to find which account the
    domain belongs to. Pass a specific profile with the global --profile
    option to skip that search and query just that one.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    last_error: Optional[HRDError] = None
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            d = client.get_domain_details(domain)
        except HRDError as e:
            last_error = e
            continue

        click.echo(f"Domain:      {d.name}")
        click.echo(f"Status:      {d.status}")
        click.echo(f"Created:     {d.create_date.strftime('%Y-%m-%d') if d.create_date else 'unknown'}")
        click.echo(f"Expires:     {d.expiry_date.strftime('%Y-%m-%d') if d.expiry_date else 'unknown'}")

        privacy_str = "enabled" if d.privacy else "disabled"
        if d.privacy_protection_date:
            privacy_str += f" (since {d.privacy_protection_date.strftime('%Y-%m-%d')})"
        click.echo(f"Privacy:     {privacy_str}")

        if d.nameservers:
            click.echo(f"Nameservers: {', '.join(d.nameservers)}")
        if d.hosts:
            hosts_str = ", ".join(f"{h.get('name')} ({', '.join(h.get('ips', []))})" for h in d.hosts)
            click.echo(f"Glue hosts:  {hosts_str}")
        if d.dnssec_records:
            click.echo(f"DNSSEC:      {len(d.dnssec_records)} record(s)")
        if d.action_ids:
            click.echo(f"Actions:     {', '.join(str(i) for i in d.action_ids)}")

        click.echo("\nOwner:")
        if d.owner_id is not None:
            click.echo(f"  ID:      {d.owner_id}")
        if d.owner:
            click.echo(f"  Name:    {d.owner.name}")
            if d.owner.type:
                click.echo(f"  Type:    {d.owner.type}")
            if d.owner.id_number:
                click.echo(f"  Tax/ID:  {d.owner.id_number}")
            if d.owner.email:
                click.echo(f"  Email:   {d.owner.email}")
            address = ", ".join(p for p in (d.owner.street, d.owner.postcode, d.owner.city, d.owner.country) if p)
            if address:
                click.echo(f"  Address: {address}")
            if d.owner.landline_phone:
                click.echo(f"  Phone:   {d.owner.landline_phone}")
            if d.owner.mobile_phone:
                click.echo(f"  Mobile:  {d.owner.mobile_phone}")
        else:
            click.echo("  unknown")
        return

    click.echo(f"Error: {last_error}" if last_error else f"Domain '{domain}' not found in any configured profile.")


@cli.command(name="owner-info")
@click.argument("owner_id", type=int)
@click.pass_obj
def owner_info(obj, owner_id):
    """Show a subscriber's (abonent's) details and every domain they own.

    Searches every configured profile by default to find which account the
    subscriber belongs to. Pass a specific profile with the global --profile
    option to skip that search and query just that one.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    last_error: Optional[HRDError] = None
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            owner = client.get_owner(owner_id)
        except HRDError as e:
            last_error = e
            continue

        click.echo(f"ID:      {owner_id}")
        click.echo(f"Name:    {owner.name}")
        if owner.type:
            click.echo(f"Type:    {owner.type}")
        if owner.id_number:
            click.echo(f"Tax/ID:  {owner.id_number}")
        if owner.email:
            click.echo(f"Email:   {owner.email}")
        address = ", ".join(p for p in (owner.street, owner.postcode, owner.city, owner.country) if p)
        if address:
            click.echo(f"Address: {address}")
        if owner.landline_phone:
            click.echo(f"Phone:   {owner.landline_phone}")
        if owner.mobile_phone:
            click.echo(f"Mobile:  {owner.mobile_phone}")

        owned_domains = [d for d in client.list_domains() if d.owner_id == owner_id]
        click.echo(f"\nDomains ({len(owned_domains)}):")
        for d in owned_domains:
            expiry_str = d.expiry_date.strftime("%Y-%m-%d") if d.expiry_date else "unknown"
            click.echo(f"  {d.name:30} | {expiry_str:10} | {d.status}")
        return

    click.echo(f"Error: {last_error}" if last_error else f"Owner id {owner_id} not found in any configured profile.")


@cli.command()
@click.option("--limit", default=20, help="Number of most recent operations to show per profile")
@click.pass_obj
def history(obj, limit):
    """Show account operation history (domain purchases, renewals, etc.).

    Shows history for every configured profile (partner/reseller account)
    by default, merged into one table sorted by date (newest first). Pass a
    specific profile with the global --profile option to restrict it to
    just that one.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    rows = []
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            for entry in client.get_history(limit=limit):
                rows.append((p_name or "default", entry))
        except HRDError as e:
            click.echo(f"Error processing profile {p_name or 'default'}: {e}")

    if not rows:
        click.echo("No history found.")
        return

    rows.sort(key=lambda r: r[1].date or datetime.min, reverse=True)

    click.echo(f"{'DATE':19} | {'PROFILE':12} | {'TYPE':10} | {'OBJECT':30} | {'COST':>10} | STATUS")
    for profile, entry in rows:
        date_str = entry.date.strftime("%Y-%m-%d %H:%M:%S") if entry.date else "unknown"
        target = entry.object_name or entry.object
        cost_str = f"{entry.amount:.2f}" if entry.amount is not None else "-"
        click.echo(f"{date_str:19} | {profile:12} | {entry.type:10} | {target:30} | {cost_str:>10} | {entry.status}")


@cli.command()
@click.argument("domain")
@click.option("--period", default=1, help="Renewal period in years")
@click.pass_obj
def renew(obj, domain, period):
    """Renew a specific domain.

    Searches every configured profile by default to find which account the
    domain belongs to. Pass a specific profile with the global --profile
    option to skip that search and target just that one.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    click.echo(f"Renewing domain {domain} for {period} year(s)...")

    last_error: Optional[HRDError] = None
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            action_id = client.renew_domain(domain, period)
        except HRDError as e:
            last_error = e
            continue

        click.echo(f"Success! Action ID: {action_id}")
        return

    click.echo(f"Error: {last_error}" if last_error else f"Domain '{domain}' not found in any configured profile.")


@cli.command(name="nameservers")
@click.argument("domain")
@click.argument("nameservers", nargs=-1, required=True)
@click.pass_obj
def nameservers_cmd(obj, domain, nameservers):
    """Update a domain's nameservers.

    Pass the new nameserver hostnames as extra arguments, e.g.
    'hrd nameservers example.com ns1.example.com ns2.example.com'. The API
    requires at least 2 nameservers. Searches every configured profile by
    default to find which account the domain belongs to.
    """
    if len(nameservers) < 2:
        click.echo("Error: at least 2 nameservers are required.")
        return

    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    last_error: Optional[HRDError] = None
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            action_id = client.update_nameservers(domain, list(nameservers))
        except HRDError as e:
            last_error = e
            continue

        click.echo(f"Nameservers for {domain} updated to: {', '.join(nameservers)}")
        if action_id is not None:
            click.echo(f"Action ID: {action_id}")
        return

    click.echo(f"Error: {last_error}" if last_error else f"Domain '{domain}' not found in any configured profile.")


@cli.group()
def host():
    """Manage glue host records (nameservers hosted under a domain you control)."""
    pass


@host.command(name="list")
@click.pass_obj
def host_list(obj):
    """List glue hosts.

    Processes every configured profile by default.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        click.echo(f"\n--- Profile: {p_name or 'default'} ---")
        try:
            client = ctx_profile.get_client()
            client.login()
            hosts = client.list_hosts()
            if not hosts:
                click.echo("No hosts found.")
            for h in hosts:
                click.echo(h)
        except HRDError as e:
            click.echo(f"Error processing profile {p_name or 'default'}: {e}")


@host.command(name="info")
@click.argument("name")
@click.pass_obj
def host_info(obj, name):
    """Show a glue host's configured IP addresses.

    Searches every configured profile by default.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    last_error: Optional[HRDError] = None
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            info = client.get_host(name)
        except HRDError as e:
            last_error = e
            continue

        click.echo(f"Name: {info.get('name', name)}")
        click.echo(f"IPs:  {', '.join(info.get('ips', [])) or 'none'}")
        return

    click.echo(f"Error: {last_error}" if last_error else f"Host '{name}' not found in any configured profile.")


@host.command(name="create")
@click.argument("name")
@click.option("--ipv4", multiple=True, help="IPv4 address (repeatable)")
@click.option("--ipv6", multiple=True, help="IPv6 address (repeatable)")
@click.pass_obj
def host_create(obj, name, ipv4, ipv6):
    """Create a glue host record.

    Searches every configured profile by default to find which account the
    parent domain belongs to.
    """
    if not ipv4 and not ipv6:
        click.echo("Error: provide at least one --ipv4 or --ipv6 address.")
        return

    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    last_error: Optional[HRDError] = None
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            action_id = client.create_host(name, list(ipv4), list(ipv6))
        except HRDError as e:
            last_error = e
            continue

        click.echo(f"Host {name} created.")
        if action_id is not None:
            click.echo(f"Action ID: {action_id}")
        return

    click.echo(f"Error: {last_error}" if last_error else "Could not create host in any configured profile.")


@host.command(name="update")
@click.argument("name")
@click.option("--ipv4", multiple=True, help="IPv4 address (repeatable)")
@click.option("--ipv6", multiple=True, help="IPv6 address (repeatable)")
@click.pass_obj
def host_update(obj, name, ipv4, ipv6):
    """Update a glue host's IP addresses.

    Searches every configured profile by default.
    """
    if not ipv4 and not ipv6:
        click.echo("Error: provide at least one --ipv4 or --ipv6 address.")
        return

    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    last_error: Optional[HRDError] = None
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            action_id = client.update_host(name, list(ipv4), list(ipv6))
        except HRDError as e:
            last_error = e
            continue

        click.echo(f"Host {name} updated.")
        if action_id is not None:
            click.echo(f"Action ID: {action_id}")
        return

    click.echo(f"Error: {last_error}" if last_error else f"Host '{name}' not found in any configured profile.")


@host.command(name="delete")
@click.argument("name")
@click.pass_obj
def host_delete(obj, name):
    """Delete a glue host record.

    Searches every configured profile by default.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    last_error: Optional[HRDError] = None
    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        try:
            client = ctx_profile.get_client()
            client.login()
            action_id = client.delete_host(name)
        except HRDError as e:
            last_error = e
            continue

        click.echo(f"Host {name} deleted.")
        if action_id is not None:
            click.echo(f"Action ID: {action_id}")
        return

    click.echo(f"Error: {last_error}" if last_error else f"Host '{name}' not found in any configured profile.")


@cli.command()
@click.option("--limit", default=20, help="Maximum number of notifications to show/drain per profile")
@click.option("--ack", is_flag=True, help="Acknowledge each notification after showing it, advancing the queue")
@click.pass_obj
def notifications(obj, limit, ack):
    """Show pending account notifications (poll queue).

    Without --ack, only peeks at the oldest pending notification per profile
    (the API always returns the same one until it is acknowledged). With
    --ack, drains up to --limit notifications per profile, acknowledging
    each one as it is shown so the next call returns the following one.
    Processes every configured profile by default.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        click.echo(f"\n--- Profile: {p_name or 'default'} ---")
        try:
            client = ctx_profile.get_client()
            client.login()
            shown = 0
            while shown < limit:
                note = client.get_next_notification()
                if not note:
                    break

                target = note.get("objectName") or note.get("objectId") or ""
                added = note.get("added") or "unknown"
                click.echo(f"#{note.get('id')} | {added:19} | {note.get('object')} {target} | {note.get('action')}")
                shown += 1

                if ack and note.get("id"):
                    client.ack_notification(int(note["id"]))
                else:
                    break

            if shown == 0:
                click.echo("No pending notifications.")
        except HRDError as e:
            click.echo(f"Error processing profile {p_name or 'default'}: {e}")


@cli.command(name="owner-list")
@click.option("--details", is_flag=True, help="Fetch each subscriber's name too (one extra API call per subscriber)")
@click.pass_obj
def owner_list(obj, details):
    """List every subscriber (abonent) id on the account.

    Processes every configured profile by default.
    """
    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    for p_name in profiles_to_process:
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)
        click.echo(f"\n--- Profile: {p_name or 'default'} ---")
        try:
            client = ctx_profile.get_client()
            client.login()
            owner_ids = client.list_owner_ids()
            if not owner_ids:
                click.echo("No subscribers found.")
                continue

            for oid in owner_ids:
                if details:
                    try:
                        owner = client.get_owner(oid)
                        click.echo(f"{oid:10} | {owner.name}")
                    except HRDError as e:
                        click.echo(f"{oid:10} | Error: {e}")
                else:
                    click.echo(str(oid))
        except HRDError as e:
            click.echo(f"Error processing profile {p_name or 'default'}: {e}")


@cli.command()
@click.option("--days", default=30, help="Days until expiry for automatic renewal")
@click.option("--dry-run", is_flag=True, help="Don't actually perform renewal")
@click.option("--no-ask", is_flag=True, help="Don't ask for confirmation before renewing each domain")
@click.pass_obj
def auto_renew(obj, days, dry_run, no_ask):
    """Automatically renew expiring domains.

    Processes all configured profiles by default. Pass a specific profile
    with the global --profile option to restrict it to just that one.
    """

    profiles_to_process = obj.get_profiles_to_process()
    if not profiles_to_process:
        click.echo("No profiles configured. Use 'hrd profile add' to set up credentials.")
        return

    for p_name in profiles_to_process:
        # Create a fresh context per profile, unless the user pinned one explicitly
        ctx_profile = obj if obj.explicit_profile else CLIContext(p_name, debug=obj.debug)

        click.echo(f"\n--- Processing profile: {p_name or 'default'} ---")
        try:
            client = ctx_profile.get_client()
            client.login()
            click.echo(f"Checking for domains expiring within {days} days...")
            domains = client.list_domains()
            expiring = [d for d in domains if d.is_expiring_soon(days)]

            if not expiring:
                click.echo("No domains found for renewal.")
                continue

            for d in expiring:
                expiry_str = d.expiry_date.strftime("%Y-%m-%d") if d.expiry_date else "unknown"
                if dry_run:
                    click.echo(f"[DRY RUN] Would renew {d.name} (expires {expiry_str})")
                else:
                    if not no_ask:
                        if not click.confirm(f"Renew {d.name} (expires {expiry_str})?", default=False):
                            click.echo(f"Skipping {d.name}")
                            continue

                    click.echo(f"Renewing {d.name}...")
                    try:
                        action_id = client.renew_domain(d.name)
                        click.echo(f"  Success: {action_id}")
                    except HRDError as e:
                        click.echo(f"  Failed: {e}")
        except Exception as e:
            click.echo(f"Error processing profile {p_name or 'default'}: {e}")


if __name__ == "__main__":
    cli()
