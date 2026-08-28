"""Complete synthetic home and environment matrix for sandbox decoys."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DecoyFileSpec:
    path: str
    key: str
    format: str = "text"


FILE_SPECS = (
    DecoyFileSpec(".ssh/id_ed25519", "ssh_ed25519", "private_key"),
    DecoyFileSpec(".ssh/id_rsa", "ssh_rsa", "private_key"),
    DecoyFileSpec(".ssh/config", "ssh_config", "ssh_config"),
    DecoyFileSpec(".ssh/known_hosts", "ssh_known_hosts", "known_hosts"),
    DecoyFileSpec(".aws/credentials", "aws_credentials", "aws_credentials"),
    DecoyFileSpec(".aws/config", "aws_config", "profile"),
    DecoyFileSpec(".gitconfig", "git_config", "git_config"),
    DecoyFileSpec(".npmrc", "npm_token", "assignment"),
    DecoyFileSpec(".pypirc", "pypi_token", "assignment"),
    DecoyFileSpec(".netrc", "netrc", "netrc"),
    DecoyFileSpec(".docker/config.json", "docker_config", "json"),
    DecoyFileSpec(".config/gcloud/credentials.db", "gcloud", "text"),
    DecoyFileSpec(".azure/accessTokens.json", "azure", "json"),
    DecoyFileSpec(".kube/config", "kube_config", "profile"),
    DecoyFileSpec(".bash_history", "bash_history", "history"),
    DecoyFileSpec(".zsh_history", "zsh_history", "history"),
    DecoyFileSpec(".config/google-chrome/Default/Cookies", "chrome_cookie", "sqlite"),
    *tuple(
        DecoyFileSpec(f"{directory}/document-{index}.txt", f"{directory.lower()}_{index}")
        for directory in ("Documents", "Desktop", "Downloads")
        for index in range(1, 6)
    ),
)

ENVIRONMENT_KEYS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "SLACK_TOKEN",
    "NOTION_TOKEN",
    "DATABASE_URL",
    "STRIPE_SECRET_KEY",
    "NPM_TOKEN",
    "PYPI_TOKEN",
    "DOCKER_AUTH_CONFIG",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "KUBECONFIG",
    "SSH_AUTH_SOCK",
    "SENTRY_AUTH_TOKEN",
    "TWILIO_AUTH_TOKEN",
    "SENDGRID_API_KEY",
    "HUGGINGFACE_TOKEN",
    "CLOUDFLARE_API_TOKEN",
    "VERCEL_TOKEN",
    "HEROKU_API_KEY",
    "POSTGRES_PASSWORD",
    "REDIS_URL",
    "MONGODB_URI",
)


def formatted_content(spec: DecoyFileSpec, token: bytes) -> bytes:
    text = token.decode("ascii")
    if spec.format == "private_key":
        return (
            f"-----BEGIN OPENSSH PRIVATE KEY-----\n{text}\n-----END OPENSSH PRIVATE KEY-----\n"
        ).encode()
    if spec.format == "ssh_config":
        return f"Host decoy.example\n  IdentityFile ~/{spec.path}\n  User {text}\n".encode()
    if spec.format == "known_hosts":
        return f"decoy.example ssh-ed25519 {text}\n".encode()
    if spec.format == "aws_credentials":
        return (
            f"[default]\naws_access_key_id = AKIA{text}\naws_secret_access_key = {text}\n"
        ).encode()
    if spec.format == "profile":
        return f"[default]\ncredential = {text}\n".encode()
    if spec.format == "git_config":
        return f"[user]\n\tname = {json.dumps(text)}\n\temail = decoy@example.invalid\n".encode()
    if spec.format == "assignment":
        return f"token={text}\n".encode()
    if spec.format == "netrc":
        return f"machine decoy.example login pano password {text}\n".encode()
    if spec.format == "json":
        return (json.dumps({"synthetic": text}, separators=(",", ":")) + "\n").encode()
    if spec.format == "history":
        return f"echo synthetic-{text}\n".encode()
    if spec.format == "sqlite":
        return b"SQLite format 3\x00" + token + b"\x00" * 64
    return f"PANOPTICON SYNTHETIC CONTENT {text}\n".encode()
