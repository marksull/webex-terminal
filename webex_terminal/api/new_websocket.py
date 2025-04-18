"""
Websocket client for receiving real-time events from Webex.
"""
import json
import asyncio
import uuid
import requests
import websockets
import base64
from enum import Enum
from typing import Dict, Callable, Optional, Any, List

from webex_terminal.auth.auth import get_token
from webex_terminal.api.client import WebexClient, WebexAPIError


class HydraTypes(Enum):
    MESSAGE = "MESSAGE"
    ATTACHMENT_ACTION = "ATTACHMENT_ACTION"


class WebexWebsocket:
    """Websocket client for Webex events."""

    def __init__(self):
        """Initialize the websocket client."""
        self.client = WebexClient()
        self.websocket = None
        self.device_info = None
        self.running = False
        self.message_callback = None
        self.current_room_id = None
        self.message_loop_task = None
        self.reconnection_count = 0
        self.max_reconnection_count = 5
        self.HYDRA_PREFIX = "ciscospark://us"

    def reset_reconnection_count(self):
        """Reset the reconnection counter."""
        self.reconnection_count = 0

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

        result = response.json()
        self.device_info = result
        return result

    async def _get_device_info(self) -> Dict:
        """Get the device info, registering a new device if necessary."""
        # Register a device if we don't have one
        if not self.device_info:
            await self._register_device()

        return self.device_info

    async def connect(self):
        """Connect to the Webex websocket."""
        # Clean up any existing resources
        await self._cleanup_resources()

        try:
            # Get the device info
            device_info = await self._get_device_info()
            websocket_url = device_info.get('webSocketUrl')

            if not websocket_url:
                raise ValueError("No websocket URL found in device info")

            self.running = True
            self.message_loop_task = asyncio.create_task(self._message_loop())

            return True
        except Exception as e:
            self.running = False
            return False

    async def _cleanup_resources(self):
        """Clean up any existing resources."""
        # Cancel any existing message loop task
        if self.message_loop_task and not self.message_loop_task.done():
            self.message_loop_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self.message_loop_task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            finally:
                self.message_loop_task = None

        # Close any existing websocket connection
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            finally:
                self.websocket = None

    async def disconnect(self):
        """Disconnect from the Webex websocket."""
        # Set running to False first to signal tasks to stop
        self.running = False

        # Clean up resources
        await self._cleanup_resources()

    async def _message_loop(self):
        """Handle incoming websocket messages using a simpler approach based on the reference implementation."""
        try:
            while self.running:
                try:
                    # Get the device info and websocket URL
                    device_info = await self._get_device_info()
                    websocket_url = device_info.get('webSocketUrl')

                    if not websocket_url:
                        await asyncio.sleep(5)
                        continue

                    # Connect to the websocket
                    async with websockets.connect(websocket_url) as ws:
                        self.websocket = ws

                        # Send authorization message
                        token_data = get_token()
                        if not token_data:
                            await asyncio.sleep(5)
                            continue

                        auth_msg = {
                            "id": str(uuid.uuid4()),
                            "type": "authorization",
                            "data": {"token": "Bearer " + token_data['access_token']}
                        }

                        await ws.send(json.dumps(auth_msg))

                        # Reset reconnection count on successful connection
                        self.reset_reconnection_count()

                        # Process messages
                        while self.running:
                            try:
                                message = await ws.recv()

                                # Process the message in the current task
                                await self._process_message(message)
                            except websockets.exceptions.ConnectionClosed:
                                break
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                # Continue to next message
                                pass

                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Increment reconnection count
                    self.reconnection_count += 1

                    if self.reconnection_count >= self.max_reconnection_count:
                        break

                    # Wait before retrying
                    retry_delay = min(30, 2 ** self.reconnection_count)

                    try:
                        await asyncio.sleep(retry_delay)
                    except asyncio.CancelledError:
                        raise

                # Clear websocket reference
                self.websocket = None

        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            # Clear websocket reference
            self.websocket = None

    async def _process_message(self, message_str: str):
        """Process a websocket message."""
        try:
            # Parse the message
            data = json.loads(message_str)

            # Handle the message
            await self._handle_message(data)
        except Exception:
            pass

    async def _handle_message(self, data: Dict):
        """Handle a websocket message."""
        # Check if this is an activity event
        event_type = data.get('data', {}).get('eventType')

        if event_type == 'conversation.activity':
            activity = data['data']['activity']

            # Check if this is a message event - accept both 'post' and 'share' verbs
            verb = activity.get('verb')

            if verb in ['post', 'share'] and self.message_callback:
                # Get the message details - use the ID from the activity
                message_id = activity.get('id')

                # Try different locations for the room ID
                room_id = activity.get('target', {}).get('globalId')

                if not room_id:
                    # Fallback to target.id if globalId is not available
                    room_id = activity.get('target', {}).get('id')

                if not room_id:
                    # Try to get room ID from the 'object' field if available
                    room_id = activity.get('object', {}).get('roomId')

                # Only process messages for the current room and if we have a valid message ID
                if room_id == self.current_room_id and message_id:
                    try:
                        # Get the full message details - convert UUID to Hydra ID first
                        hydra_id = self.build_hydra_id(message_id)
                        message = self.client.get_message(hydra_id)

                        # Call the callback with the message
                        await self.message_callback(message)

                    except WebexAPIError:
                        pass

    def set_room(self, room_id: str):
        """Set the current room to listen for messages."""
        self.current_room_id = room_id

    def build_hydra_id(self, uuid, message_type=HydraTypes.MESSAGE.value):
        """
        Convert a UUID into Hydra ID that includes geo routing
        :param uuid: The UUID to be encoded
        :param message_type: The type of message to be encoded
        :return (str): The encoded uuid
        """
        return (
            base64.b64encode(f"{self.HYDRA_PREFIX}/{message_type}/{uuid}".encode("ascii")).decode(
                "ascii"
            )
            if "-" in uuid
            else uuid
        )

    def on_message(self, callback: Callable[[Dict], Any]):
        """Set the callback for new messages."""
        self.message_callback = callback


async def create_websocket_client() -> WebexWebsocket:
    """Create and connect a websocket client."""
    client = WebexWebsocket()

    try:
        # Yield control back to the event loop before connecting
        await asyncio.sleep(0)

        success = await client.connect()
        if not success:
            raise Exception("Failed to connect to Webex websocket")

        # Yield control back to the event loop after connecting
        await asyncio.sleep(0)

        return client
    except Exception as e:
        # Make sure to clean up resources if connection fails
        try:
            await client.disconnect()
        except Exception:
            pass
        # Re-raise the original exception
        raise
