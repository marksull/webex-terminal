"""
Authentication module for Webex Terminal.
Handles OAuth2 authentication and token management.
"""
import os
import time
import webbrowser
import http.server
import socketserver
import urllib.parse
import requests
import threading
from typing import Dict, Optional, Tuple

from webex_terminal.config import (
    load_config,
    save_token,
    load_token,
    clear_token,
)


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""
    
    def __init__(self, *args, **kwargs):
        self.auth_code = None
        self.error = None
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET request to the callback URL."""
        query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        
        if self.path.startswith('/callback'):
            if 'code' in query_components:
                self.server.auth_code = query_components['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<html><head><title>Authentication Successful</title></head>')
                self.wfile.write(b'<body><h1>Authentication Successful!</h1>')
                self.wfile.write(b'<p>You can now close this window and return to the terminal.</p>')
                self.wfile.write(b'</body></html>')
            elif 'error' in query_components:
                self.server.error = query_components['error'][0]
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<html><head><title>Authentication Error</title></head>')
                self.wfile.write(b'<body><h1>Authentication Error</h1>')
                self.wfile.write(f'<p>Error: {self.server.error}</p>'.encode())
                self.wfile.write(b'</body></html>')
            else:
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<html><head><title>Invalid Request</title></head>')
                self.wfile.write(b'<body><h1>Invalid Request</h1>')
                self.wfile.write(b'<p>Missing required parameters.</p>')
                self.wfile.write(b'</body></html>')
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><head><title>Not Found</title></head>')
            self.wfile.write(b'<body><h1>Not Found</h1>')
            self.wfile.write(b'<p>The requested resource was not found.</p>')
            self.wfile.write(b'</body></html>')
    
    def log_message(self, format, *args):
        """Suppress log messages."""
        return


class OAuthCallbackServer(socketserver.TCPServer):
    """TCP server for OAuth callback."""
    
    def __init__(self, server_address, RequestHandlerClass):
        self.auth_code = None
        self.error = None
        super().__init__(server_address, RequestHandlerClass)


def start_callback_server(port: int = 8080) -> OAuthCallbackServer:
    """Start the callback server for OAuth authentication."""
    server = OAuthCallbackServer(('localhost', port), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return server


def stop_callback_server(server: OAuthCallbackServer):
    """Stop the callback server."""
    server.shutdown()
    server.server_close()


def get_authorization_url(client_id: str) -> str:
    """Get the authorization URL for OAuth authentication."""
    config = load_config()
    params = {
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': config['redirect_uri'],
        'scope': config['scope'],
    }
    auth_url = f"{config['auth_url']}?{urllib.parse.urlencode(params)}"
    return auth_url


def exchange_code_for_token(client_id: str, client_secret: str, code: str) -> Dict:
    """Exchange authorization code for access token."""
    config = load_config()
    data = {
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'redirect_uri': config['redirect_uri'],
    }
    response = requests.post(config['token_url'], data=data)
    response.raise_for_status()
    return response.json()


def refresh_token(client_id: str, client_secret: str, refresh_token: str) -> Dict:
    """Refresh the access token using the refresh token."""
    config = load_config()
    data = {
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
    }
    response = requests.post(config['token_url'], data=data)
    response.raise_for_status()
    return response.json()


def authenticate(client_id: str, client_secret: str) -> Tuple[bool, Optional[str]]:
    """
    Authenticate with Webex using OAuth2.
    
    Returns:
        Tuple[bool, Optional[str]]: (success, error_message)
    """
    # Start the callback server
    server = start_callback_server()
    
    try:
        # Get the authorization URL and open it in a browser
        auth_url = get_authorization_url(client_id)
        print(f"Opening browser for authentication: {auth_url}")
        webbrowser.open(auth_url)
        
        # Wait for the callback
        print("Waiting for authentication callback...")
        max_wait_time = 300  # 5 minutes
        start_time = time.time()
        
        while server.auth_code is None and server.error is None:
            if time.time() - start_time > max_wait_time:
                return False, "Authentication timed out"
            time.sleep(0.1)
        
        if server.error:
            return False, f"Authentication error: {server.error}"
        
        # Exchange the authorization code for an access token
        token_data = exchange_code_for_token(client_id, client_secret, server.auth_code)
        
        # Save the token
        save_token(token_data)
        
        return True, None
    
    except Exception as e:
        return False, str(e)
    
    finally:
        # Stop the callback server
        stop_callback_server(server)


def get_token() -> Optional[Dict]:
    """
    Get the current access token, refreshing if necessary.
    
    Returns:
        Optional[Dict]: The token data or None if not authenticated
    """
    token_data = load_token()
    
    if token_data is None:
        return None
    
    # Check if the token is expired
    expires_at = token_data.get('expires_at')
    if expires_at is None:
        # If we don't have an expires_at field, calculate it
        if 'expires_in' in token_data:
            token_data['expires_at'] = time.time() + token_data['expires_in']
            save_token(token_data)
            expires_at = token_data['expires_at']
        else:
            # If we don't have expires_in either, assume the token is valid
            return token_data
    
    # If the token is expired, refresh it
    if time.time() > expires_at - 60:  # Refresh 60 seconds before expiration
        try:
            # We need client credentials to refresh the token
            # In a real application, these would be stored securely
            # For this example, we'll assume they're in environment variables
            client_id = os.environ.get('WEBEX_CLIENT_ID')
            client_secret = os.environ.get('WEBEX_CLIENT_SECRET')
            
            if not client_id or not client_secret:
                print("Client credentials not found in environment variables")
                return None
            
            token_data = refresh_token(client_id, client_secret, token_data['refresh_token'])
            token_data['expires_at'] = time.time() + token_data['expires_in']
            save_token(token_data)
        except Exception as e:
            print(f"Error refreshing token: {e}")
            return None
    
    return token_data


def is_authenticated() -> bool:
    """Check if the user is authenticated."""
    return get_token() is not None


def logout():
    """Log out by clearing the stored token."""
    clear_token()