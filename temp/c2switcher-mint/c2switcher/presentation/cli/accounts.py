"""Account management commands."""

from __future__ import annotations

import json
from typing import Optional

import click
from rich import box
from rich.panel import Panel
from rich.table import Table

from ...constants import CREDENTIALS_PATH, console
from ...infrastructure.locking import acquire_lock
from ...infrastructure.factory import ServiceFactory
from ...core.errors import AccountNotFound, InvalidCredentials, ProfileFetchError
from ...utils import mask_email


@click.command()
@click.option('--nickname', '-n', help='Optional nickname for the account')
@click.option(
    '--creds-file',
    '-f',
    type=click.Path(exists=True),
    help='Path to credentials JSON file',
)
def add(nickname: Optional[str], creds_file: Optional[str]):
    """Add a new account from credentials file or current .credentials.json."""
    acquire_lock()
    factory = ServiceFactory()

    try:
        if creds_file:
            with open(creds_file, 'r', encoding='utf-8') as handle:
                credentials_json = handle.read()
        else:
            if not CREDENTIALS_PATH.exists():
                console.print(f'[red]Error: {CREDENTIALS_PATH} not found[/red]')
                console.print('[yellow]Please specify a credentials file with --creds-file[/yellow]')
                return
            with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as handle:
                credentials_json = handle.read()

        account_service = factory.get_account_service()
        account, is_new = account_service.add_account(credentials_json, nickname=nickname)

        console.print(
            Panel(
                f'[green]✓[/green] Account {"added" if is_new else "updated"} successfully\n\n'
                f'Index: [bold]{account.index_num}[/bold]\n'
                f'Email: [bold]{account.email}[/bold]\n'
                f'Name: {account.display_name or account.full_name}\n'
                f'Nickname: {nickname or "[dim]none[/dim]"}',
                title='Account Added' if is_new else 'Account Updated',
                border_style='green',
            )
        )

    except (InvalidCredentials, ProfileFetchError) as exc:
        console.print(f'[red]Error: {exc}[/red]')
    except Exception as exc:
        console.print(f'[red]Error adding account: {exc}[/red]')
    finally:
        factory.close()


@click.command(name='ls')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
def list_accounts_cmd(output_json: bool):
    """List all accounts."""
    factory = ServiceFactory()

    try:
        account_service = factory.get_account_service()
        accounts = account_service.list_accounts()

        if output_json:
            result = []
            for acc in accounts:
                result.append(
                    {
                        'index': acc.index_num,
                        'nickname': acc.nickname,
                        'email': acc.email,
                        'full_name': acc.full_name,
                        'display_name': acc.display_name,
                        'has_claude_max': acc.has_claude_max,
                        'has_claude_pro': acc.has_claude_pro,
                        'org_type': acc.org_type,
                        'rate_limit_tier': acc.rate_limit_tier,
                        'has_api_key': acc.api_key is not None,
                    }
                )
            print(json.dumps(result, indent=2))
            return

        if not accounts:
            console.print("[yellow]No accounts found. Add one with 'c2switcher add'[/yellow]")
            return

        table = Table(title='Claude Code Accounts', box=box.ROUNDED)
        table.add_column('Index', style='cyan', justify='center')
        table.add_column('Nickname', style='magenta')
        table.add_column('Email', style='green')
        table.add_column('Name', style='blue')
        table.add_column('Type', justify='center')
        table.add_column('Tier', style='yellow')
        table.add_column('Key', justify='center')

        for acc in accounts:
            account_type = 'Max' if acc.has_claude_max else 'Pro' if acc.has_claude_pro else 'Free'
            type_color = 'green' if acc.has_claude_max else 'blue' if acc.has_claude_pro else 'dim'
            key_status = '[green]✓[/green]' if acc.api_key else '[dim]○[/dim]'

            table.add_row(
                str(acc.index_num),
                acc.nickname or '[dim]--[/dim]',
                acc.email,
                acc.display_name or acc.full_name or '[dim]--[/dim]',
                f'[{type_color}]{account_type}[/{type_color}]',
                acc.rate_limit_tier or '[dim]--[/dim]',
                key_status,
            )

        console.print(table)

    finally:
        factory.close()


@click.command(name='current')
@click.option(
    '--format',
    type=click.Choice(['default', 'prompt']),
    default='default',
    help='Output format (default, prompt)',
)
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
def current(format: str, output_json: bool):
    """Show currently selected account from credentials file."""
    if not CREDENTIALS_PATH.exists():
        if output_json:
            print(json.dumps({'error': 'No credentials file found'}))
        else:
            console.print('[yellow]No credentials file found[/yellow]')
            console.print(
                "[yellow]→ Run 'c2switcher optimal' or 'c2switcher switch <account>' to select an account[/yellow]"
            )
        return

    factory = ServiceFactory()

    try:
        with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as handle:
            current_creds = json.load(handle)

        current_oauth = current_creds.get('claudeAiOauth', {})
        current_token = current_oauth.get('accessToken')
        current_refresh = current_oauth.get('refreshToken')

        if not current_token:
            if output_json:
                print(json.dumps({'error': 'No access token in credentials file'}))
            else:
                console.print('[yellow]No access token in credentials file[/yellow]')
            return

        account_service = factory.get_account_service()
        accounts = account_service.list_accounts()
        current_account = None

        for acc in accounts:
            matched = False
            if current_refresh:
                # OAuth account: match by refresh token (stable across access token refreshes).
                # Claude Code refreshes access tokens on its own schedule, writing new tokens to
                # the credentials file without updating c2switcher's DB — but the refresh token
                # stays the same, so this identifies the account reliably.
                acc_creds = acc.get_credentials()
                acc_refresh = acc_creds.get('claudeAiOauth', {}).get('refreshToken')
                if acc_refresh and acc_refresh == current_refresh:
                    matched = True
            elif acc.api_key and acc.api_key == current_token:
                # API key account: credentials file stores the api_key as accessToken with no refreshToken
                matched = True
            else:
                # Fallback: access token match (may miss if Claude Code independently refreshed the token)
                acc_creds = acc.get_credentials()
                acc_token = acc_creds.get('claudeAiOauth', {}).get('accessToken')
                if acc_token == current_token:
                    matched = True

            if matched:
                current_account = acc
                break

        if not current_account:
            if output_json:
                print(json.dumps({'error': 'Current account not found in database'}))
            else:
                console.print('[yellow]Current account not found in database[/yellow]')
                console.print("[yellow]→ Run 'c2switcher add' to add this account[/yellow]")
            return

        if output_json:
            print(
                json.dumps(
                    {
                        'index': current_account.index_num,
                        'nickname': current_account.nickname,
                        'email': current_account.email,
                        'full_name': current_account.full_name,
                        'display_name': current_account.display_name,
                    },
                    indent=2,
                )
            )
        elif format == 'prompt':
            nickname = current_account.nickname or current_account.email.split('@')[0]
            print(f'[{current_account.index_num}] {nickname}')
        else:
            nickname = current_account.nickname or '[dim]none[/dim]'
            masked_email = mask_email(current_account.email)
            console.print(
                Panel(
                    f'[green]Current Account (={current_account.index_num})[/green]\n\n'
                    f'Nickname: [bold]{nickname}[/bold]\n'
                    f'Email: [bold]{masked_email}[/bold]\n'
                    f'Name: {current_account.display_name or current_account.full_name or "[dim]--[/dim]"}',
                    border_style='green',
                )
            )

    except Exception as exc:
        if output_json:
            print(json.dumps({'error': str(exc)}))
        else:
            console.print(f'[red]Error: {exc}[/red]')
    finally:
        factory.close()


@click.command(name='nickname')
@click.argument('identifier')
@click.argument('new_nickname')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
def nickname_cmd(identifier: str, new_nickname: str, output_json: bool):
    """Set or update an account nickname."""
    acquire_lock()
    factory = ServiceFactory()

    try:
        account_service = factory.get_account_service()

        try:
            updated = account_service.set_nickname(identifier, new_nickname)
        except AccountNotFound:
            if output_json:
                print(json.dumps({'error': f'Account not found: {identifier}'}))
            else:
                console.print(f'[red]Account not found: {identifier}[/red]')
                console.print("[yellow]→ Run 'c2switcher ls' to see available accounts[/yellow]")
            return

        if output_json:
            print(json.dumps({
                'success': True,
                'index': updated.index_num,
                'email': updated.email,
                'nickname': updated.nickname,
            }))
        else:
            console.print(
                Panel(
                    f'[green]✓[/green] Nickname updated\n\n'
                    f'Account: [bold]{updated.email}[/bold]\n'
                    f'Nickname: [bold]{updated.nickname or "[dim]none[/dim]"}[/bold]',
                    title='Nickname Updated',
                    border_style='green',
                )
            )

    except Exception as exc:
        if output_json:
            print(json.dumps({'error': str(exc)}))
        else:
            console.print(f'[red]Error: {exc}[/red]')
    finally:
        factory.close()


@click.command(name='remove')
@click.argument('identifier')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
def remove_account_cmd(identifier: str, yes: bool, output_json: bool):
    """Remove an account by index, nickname, or email."""
    acquire_lock()
    factory = ServiceFactory()

    try:
        account_service = factory.get_account_service()

        try:
            account = account_service.get_account(identifier)
        except AccountNotFound:
            if output_json:
                print(json.dumps({'error': f'Account not found: {identifier}'}))
            else:
                console.print(f'[red]Account not found: {identifier}[/red]')
                console.print("[yellow]→ Run 'c2switcher ls' to see available accounts[/yellow]")
            return

        if not yes and not output_json:
            click.confirm(
                f'Remove account [{account.index_num}] {account.email}? This cannot be undone.',
                abort=True,
            )

        removed = account_service.remove_account(identifier)

        # Clear ~/.claude/.credentials.json if it belongs to the removed account
        if CREDENTIALS_PATH.exists():
            try:
                with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
                    current_creds = json.load(f)
                current_token = current_creds.get('claudeAiOauth', {}).get('accessToken')
                stored_creds = json.loads(removed.credentials_json)
                stored_token = stored_creds.get('claudeAiOauth', {}).get('accessToken')
                if current_token and current_token == stored_token:
                    CREDENTIALS_PATH.unlink()
            except Exception:
                pass

        if output_json:
            print(json.dumps({
                'success': True,
                'email': removed.email,
                'index': removed.index_num,
            }))
        else:
            console.print(
                Panel(
                    f'[green]✓[/green] Account removed\n\n'
                    f'Email: [bold]{removed.email}[/bold]',
                    title='Account Removed',
                    border_style='red',
                )
            )

    except click.Abort:
        console.print('[yellow]Cancelled[/yellow]')
    except Exception as exc:
        if output_json:
            print(json.dumps({'error': str(exc)}))
        else:
            console.print(f'[red]Error: {exc}[/red]')
    finally:
        factory.close()


@click.command(name='reorder')
@click.argument('identifiers', nargs=-1, required=True)
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
def reorder_accounts_cmd(identifiers: tuple, output_json: bool):
    """Reorder accounts. Specify all account identifiers in the desired new order."""
    acquire_lock()
    factory = ServiceFactory()

    try:
        account_service = factory.get_account_service()
        all_accounts = account_service.list_accounts()

        if len(identifiers) != len(all_accounts):
            msg = f'Must specify all {len(all_accounts)} account(s). Got {len(identifiers)}.'
            if output_json:
                print(json.dumps({'error': msg}))
            else:
                console.print(f'[red]Error: {msg}[/red]')
                console.print("[yellow]→ Run 'c2switcher ls' to see available accounts[/yellow]")
            return

        ordered = []
        seen_uuids = set()
        for ident in identifiers:
            try:
                acc = account_service.get_account(ident)
            except AccountNotFound:
                if output_json:
                    print(json.dumps({'error': f'Account not found: {ident}'}))
                else:
                    console.print(f'[red]Account not found: {ident}[/red]')
                    console.print("[yellow]→ Run 'c2switcher ls' to see available accounts[/yellow]")
                return
            if acc.uuid in seen_uuids:
                msg = f'Duplicate account specified: {ident}'
                if output_json:
                    print(json.dumps({'error': msg}))
                else:
                    console.print(f'[red]Error: {msg}[/red]')
                return
            seen_uuids.add(acc.uuid)
            ordered.append(acc)

        factory.get_store().reorder_accounts([acc.uuid for acc in ordered])

        if output_json:
            print(json.dumps({
                'success': True,
                'order': [
                    {'index': i, 'email': acc.email, 'nickname': acc.nickname}
                    for i, acc in enumerate(ordered)
                ],
            }))
        else:
            console.print('[green]✓[/green] Accounts reordered')

    except Exception as exc:
        if output_json:
            print(json.dumps({'error': str(exc)}))
        else:
            console.print(f'[red]Error reordering accounts: {exc}[/red]')
    finally:
        factory.close()


@click.command(name='force-refresh')
@click.argument('identifier', required=False)
def force_refresh(identifier: Optional[str]):
    """Force refresh tokens for an account (or all accounts if none specified)."""
    acquire_lock()
    factory = ServiceFactory()

    try:
        account_service = factory.get_account_service()
        credential_store = factory.get_credential_store()

        if identifier:
            try:
                account = account_service.get_account(identifier)
                accounts_to_refresh = [account]
            except AccountNotFound:
                console.print(f'[red]Account not found: {identifier}[/red]')
                console.print("[yellow]→ Run 'c2switcher ls' to see available accounts[/yellow]")
                return
        else:
            accounts_to_refresh = account_service.list_accounts()

        if not accounts_to_refresh:
            console.print('[yellow]No accounts to refresh[/yellow]')
            return

        console.print(f'[yellow]Force refreshing {len(accounts_to_refresh)} account(s)...[/yellow]\n')

        for account in accounts_to_refresh:
            account_display = f'[{account.index_num}] {account.nickname or account.email}'

            try:
                refreshed_creds = credential_store.refresh_access_token(account.credentials_json, force=True)

                # Update stored credentials
                factory.get_store().update_credentials(account.uuid, refreshed_creds)

                expires_at = refreshed_creds.get('claudeAiOauth', {}).get('expiresAt', 0)
                import time

                expires_in_hours = (expires_at - int(time.time() * 1000)) / 1000 / 3600

                console.print(f'[green]✓[/green] {account_display} - expires in {expires_in_hours:.1f}h')

            except Exception as exc:
                console.print(f'[red]✗[/red] {account_display} - Error: {exc}')

    except Exception as exc:
        console.print(f'[red]Error: {exc}[/red]')
    finally:
        factory.close()
