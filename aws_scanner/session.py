"""AWS session and profile selection."""
import os
import sys
from typing import List, Optional

import boto3
from botocore.exceptions import ProfileNotFound, NoCredentialsError, ClientError
from rich.console import Console
from rich.prompt import Prompt

console = Console()

_ENV_CREDS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")


def list_profiles() -> List[str]:
    """Return all named profiles from ~/.aws/config and ~/.aws/credentials."""
    return sorted(boto3.Session().available_profiles)


def prompt_for_profile() -> str:
    """Interactively pick a profile from the available list."""
    profiles = list_profiles()
    if not profiles:
        console.print(
            "[red]No AWS profiles found in ~/.aws/config or ~/.aws/credentials.[/red]"
        )
        console.print("Run `aws configure --profile <name>` to create one.")
        sys.exit(1)

    console.print("\n[bold cyan]Select AWS profile to scan:[/bold cyan]")
    for idx, name in enumerate(profiles, start=1):
        console.print(f"  [green]{idx}[/green]. {name}")

    choices = [str(i) for i in range(1, len(profiles) + 1)] + profiles
    answer = Prompt.ask(
        "Profile (number or name)",
        choices=choices,
        show_choices=False,
        default="1",
    )

    if answer.isdigit():
        return profiles[int(answer) - 1]
    return answer


def _clear_env_credentials() -> List[str]:
    """Remove AWS credential env vars from the current process. Returns cleared names."""
    cleared = []
    for key in _ENV_CREDS:
        if key in os.environ:
            del os.environ[key]
            cleared.append(key)
    return cleared


def build_session(profile: Optional[str]) -> boto3.Session:
    """
    Build a boto3 Session for the given profile.

    If profile is provided, AWS credential env vars are cleared first so the
    profile actually takes effect (env vars override profile settings otherwise).
    If profile is None, uses the default boto3 credential chain.
    """
    if profile:
        cleared = _clear_env_credentials()
        if cleared:
            console.print(
                f"[yellow]Unset {', '.join(cleared)} so profile "
                f"'[bold]{profile}[/bold]' takes effect.[/yellow]"
            )
        try:
            return boto3.Session(profile_name=profile)
        except ProfileNotFound as e:
            console.print(f"[red]Profile '{profile}' not found: {e}[/red]")
            sys.exit(1)
    return boto3.Session()


def describe_identity(session: boto3.Session) -> dict:
    """Call STS GetCallerIdentity to confirm which account/user we're using."""
    try:
        sts = session.client("sts")
        return sts.get_caller_identity()
    except NoCredentialsError:
        console.print(
            "[red]No AWS credentials resolved for this profile. "
            "Check ~/.aws/credentials or run `aws configure`.[/red]"
        )
        sys.exit(1)
    except ClientError as e:
        console.print(f"[red]Failed to verify AWS identity: {e}[/red]")
        sys.exit(1)
