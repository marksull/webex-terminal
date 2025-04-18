"""
Configuration settings for the Webex Terminal application.
"""
import os
import yaml
from pathlib import Path

# Default configuration directory
CONFIG_DIR = os.path.expanduser("~/.config/webex-terminal")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
TOKEN_FILE = os.path.join(CONFIG_DIR, "token.yaml")

# Webex API endpoints
WEBEX_API_BASE_URL = "https://webexapis.com/v1"
WEBEX_AUTH_URL = "https://webexapis.com/v1/authorize"
WEBEX_TOKEN_URL = "https://webexapis.com/v1/access_token"

# OAuth2 settings
REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "spark:all"

# Default configuration
DEFAULT_CONFIG = {
    "api_base_url": WEBEX_API_BASE_URL,
    "auth_url": WEBEX_AUTH_URL,
    "token_url": WEBEX_TOKEN_URL,
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPE,
}


def ensure_config_dir():
    """Ensure the configuration directory exists."""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    """Load configuration from file or create default if it doesn't exist."""
    ensure_config_dir()
    
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)


def save_config(config):
    """Save configuration to file."""
    ensure_config_dir()
    
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f)


def load_token():
    """Load OAuth token from file."""
    ensure_config_dir()
    
    if not os.path.exists(TOKEN_FILE):
        return None
    
    with open(TOKEN_FILE, "r") as f:
        return yaml.safe_load(f)


def save_token(token):
    """Save OAuth token to file."""
    ensure_config_dir()
    
    with open(TOKEN_FILE, "w") as f:
        yaml.dump(token, f)


def clear_token():
    """Clear the stored OAuth token."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)