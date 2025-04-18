"""
Websocket client for receiving real-time events from Webex.
"""
import json
import asyncio
import requests
import websockets
from typing import Dict, Callable, Optional, Any

from webex_terminal.auth.auth import get_token
from webex_terminal.api.client import WebexClient, WebexAPIError


class WebexWebsocket:
    """Websocket client for Webex events."""

    def __init__(self):
        """Initialize the websocket client."""
        self.client = WebexClient()
        self.websocket = None
        self.device_url = None
        self.running = False
        self.message_callback = None
        self.current_room_id = None
        self.message_loop_task = None

    async def _register_device(self) -> Dict:
        """Register a device with Webex to receive websocket events."""
        # Get the current user's info
        me = self.client.get_me()

        # Create a device registration
        data = {
            'deviceName': 'Webex Terminal',
            'deviceType': 'DESKTOP',
            'localizedModel': 'Desktop',
            'model': 'Desktop',
            'name': f"Webex Terminal - {me['displayName']}",
            'systemName': 'Python',
            'systemVersion': '1.0',
        }

        # Use the specific URL for device registration
        url = "https://wdm-a.wbx2.com/wdm/api/v1/devices"
        headers = self.client._get_headers()

        # Make the direct API request
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()

    async def _get_websocket_url(self) -> str:
        """Get the websocket URL for the registered device."""
        # Register a device if we don't have one
        if not self.device_url:
            device = await self._register_device()
            self.device_url = device['webSocketUrl']

        return self.device_url

    async def connect(self):
        """Connect to the Webex websocket."""
        # Cancel any existing message loop task
        if self.message_loop_task and not self.message_loop_task.done():
            self.message_loop_task.cancel()
            try:
                await self.message_loop_task
            except asyncio.CancelledError:
                pass

        # Get the websocket URL
        websocket_url = await self._get_websocket_url()

        # Connect to the websocket
        self.websocket = await websockets.connect(websocket_url)
        self.running = True

        # Start the message handling loop
        self.message_loop_task = asyncio.create_task(self._message_loop())

    async def disconnect(self):
        """Disconnect from the Webex websocket."""
        self.running = False

        # Cancel the message loop task
        if self.message_loop_task and not self.message_loop_task.done():
            self.message_loop_task.cancel()
            try:
                await self.message_loop_task
            except asyncio.CancelledError:
                pass
            self.message_loop_task = None

        # Close the websocket connection
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    async def _message_loop(self):
        """Handle incoming websocket messages."""
        while self.running:
            if not self.websocket:
                # If no websocket connection, wait and try again
                await asyncio.sleep(1)
                continue

            try:
                # Wait for a message
                message = await self.websocket.recv()

                # Parse the message
                data = json.loads(message)

                # Handle the message
                await self._handle_message(data)

            except websockets.exceptions.ConnectionClosed:
                # Connection closed, try to reconnect without starting a new message loop
                try:
                    # Get the websocket URL
                    websocket_url = await self._get_websocket_url()

                    # Reconnect to the websocket
                    self.websocket = await websockets.connect(websocket_url)
                except Exception as e:
                    print(f"Error reconnecting to websocket: {e}")
                    self.websocket = None
                    await asyncio.sleep(1)

            except Exception as e:
                print(f"Error in websocket message loop: {e}")
                # Wait a bit before trying again
                await asyncio.sleep(1)

    async def _handle_message(self, data: Dict):
        """Handle a websocket message."""
        # Check if this is an activity event
        if data.get('data', {}).get('eventType') == 'conversation.activity':
            activity = data['data']['activity']

            # Check if this is a message event
            if activity.get('verb') == 'post' and self.message_callback:
                # Get the message details
                message_id = activity.get('id')
                room_id = activity.get('target', {}).get('id')

                # Only process messages for the current room
                if room_id == self.current_room_id:
                    try:
                        # Get the full message details
                        message = self.client.get_message(message_id)

                        # Call the callback with the message
                        await self.message_callback(message)

                    except WebexAPIError as e:
                        print(f"Error getting message details: {e}")

    def set_room(self, room_id: str):
        """Set the current room to listen for messages."""
        self.current_room_id = room_id

    def on_message(self, callback: Callable[[Dict], Any]):
        """Set the callback for new messages."""
        self.message_callback = callback


async def create_websocket_client() -> WebexWebsocket:
    """Create and connect a websocket client."""
    client = WebexWebsocket()
    await client.connect()
    return client
