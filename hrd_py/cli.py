import os
import sys
import click
from .client import HRDClient
from .exceptions import HRDError
from .config import ConfigManager
from dotenv import load_dotenv

# Still load dotenv for backward compatibility or explicit override
load_dotenv(override=True)


class CLIContext:
    def __init__(self, profile=None):
        self.config_manager = ConfigManager()
        self.profile_name = profile or self.config_manager.get_default_profile_name()
        self._client = None

    def get_client(self):
        if self._client:
            return self._client

        # 1. Try from config
        profile = self.config_manager.get_profile(self.profile_name)
        if profile:
            self._client = HRDClient(profile["login"], profile["password"], profile["api_hash"])
            return self._client

        # 2. Fallback to ENV (only if no specific profile requested)
        if not self.profile_name or self.profile_name == self.config_manager.get_default_profile_name():
            login = os.getenv("HRD_LOGIN")
            password = os.getenv("HRD_PASS")
            api_hash = os.getenv("HRD_HASH")

            if all([login, password, api_hash]):
                self._client = HRDClient(login, password, api_hash)
                return self._client

        click.echo(f"Error: Missing configuration for profile '{self.profile_name or 'default'}'.")
        click.echo("Use 'hrd profile add' to set up credentials.")
        sys.exit(1)


@click.group()
@click.option("--profile", help="Use a specific profile from config")
@click.pass_context
def cli(ctx, profile):
    """HRD.pl API Command Line Interface"""
    ctx.obj = CLIContext(profile)


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
    """Show account balance"""
    client = obj.get_client()
    try:
        client.login()
        b = client.get_balance()
        click.echo(f"Profile: {obj.profile_name or 'default'}")
        click.echo(f"Current Balance: {b.balance}")
        click.echo(f"Restricted Balance: {b.restricted_balance}")
    except HRDError as e:
        click.echo(f"Error: {e}")


@cli.command()
@click.option("--all", is_flag=True, help="List all domains, not just expiring")
@click.option("--days", default=30, help="Days until expiry for filtering")
@click.pass_obj
def domains(obj, all, days):
    """List domains and their status"""
    client = obj.get_client()
    try:
        client.login()
        click.echo(f"Fetching domains for {obj.profile_name or 'default'}...")
        domains = client.list_domains()

        for d in domains:
            if all or d.is_expiring_soon(days):
                expiry_str = d.expiry_date.strftime("%Y-%m-%d") if d.expiry_date else "Unknown"
                status_str = click.style(d.status, fg="red" if d.status == "expired" else "green")
                click.echo(f"{d.name:30} | {expiry_str:10} | {status_str}")
    except HRDError as e:
        click.echo(f"Error: {e}")


@cli.command()
@click.argument("domain")
@click.option("--period", default=1, help="Renewal period in years")
@click.pass_obj
def renew(obj, domain, period):
    """Renew a specific domain"""
    client = obj.get_client()
    try:
        client.login()
        click.echo(f"Renewing domain {domain} for {period} year(s)...")
        action_id = client.renew_domain(domain, period)
        click.echo(f"Success! Action ID: {action_id}")
    except HRDError as e:
        click.echo(f"Error: {e}")


@cli.command()
@click.option("--days", default=30, help="Days until expiry for automatic renewal")
@click.option("--dry-run", is_flag=True, help="Don't actually perform renewal")
@click.option("--interactive", "-i", is_flag=True, help="Confirm each domain before renewal")
@click.option("--all-profiles", is_flag=True, help="Process all configured profiles")
@click.pass_obj
def auto_renew(obj, days, dry_run, interactive, all_profiles):
    """Automatically renew expiring domains"""

    profiles_to_process = []
    if all_profiles:
        profiles_to_process = obj.config_manager.list_profiles()
        if not profiles_to_process:
            # If no profiles in config, check if we have ENV vars as a pseudo-profile
            if os.getenv("HRD_LOGIN"):
                profiles_to_process = [None]  # Use default/env logic
    else:
        profiles_to_process = [obj.profile_name]

    for p_name in profiles_to_process:
        # Create a fresh context for each profile if processing all
        if all_profiles:
            ctx_profile = CLIContext(p_name)
        else:
            ctx_profile = obj

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
                if dry_run:
                    click.echo(f"[DRY RUN] Would renew {d.name}")
                else:
                    if interactive:
                        if not click.confirm(f"Renew {d.name}?", default=False):
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
