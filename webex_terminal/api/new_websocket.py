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
        print("Resetting reconnection count")
        self.reconnection_count = 0

    async def _register_device(self) -> Dict:
        """Register a device with Webex to receive websocket events."""
        print("Registering device with Webex...")

        # Get the current user's info
        me = self.client.get_me()
        print(f"Got user info: {me['displayName']} ({me['id']})")

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
        print(f"Device registration data: {json.dumps(data)}")

        # Use the specific URL for device registration
        url = "https://wdm-a.wbx2.com/wdm/api/v1/devices"
        headers = self.client._get_headers()

        # Make the direct API request
        print(f"Sending device registration request to {url}...")
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()

        result = response.json()
        print(f"Device registered successfully. Device ID: {result.get('id')}")
        self.device_info = result
        return result

    async def _get_device_info(self) -> Dict:
        """Get the device info, registering a new device if necessary."""
        print("Getting device info...")

        # Register a device if we don't have one
        if not self.device_info:
            print("No device info found, registering a new device...")
            await self._register_device()
        else:
            print(f"Using existing device info with websocket URL: {self.device_info.get('webSocketUrl')}")

        return self.device_info

    async def connect(self):
        """Connect to the Webex websocket."""
        print("Connecting to Webex websocket...")

        # Clean up any existing resources
        await self._cleanup_resources()

        try:
            # Get the device info
            device_info = await self._get_device_info()
            websocket_url = device_info.get('webSocketUrl')

            if not websocket_url:
                raise ValueError("No websocket URL found in device info")

            print(f"Starting message loop task...")
            self.running = True
            self.message_loop_task = asyncio.create_task(self._message_loop())
            print("Message loop task started")

            return True
        except Exception as e:
            print(f"Error connecting to websocket: {e}")
            self.running = False
            return False

    async def _cleanup_resources(self):
        """Clean up any existing resources."""
        print("Cleaning up resources...")

        # Cancel any existing message loop task
        if self.message_loop_task and not self.message_loop_task.done():
            print("Cancelling existing message loop task...")
            self.message_loop_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self.message_loop_task), timeout=2.0)
                print("Existing message loop task cancelled successfully")
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception) as e:
                print(f"Error or timeout cancelling message loop task: {e}")
            finally:
                self.message_loop_task = None
                print("Message loop task reference cleared")

        # Close any existing websocket connection
        if self.websocket:
            print("Closing existing websocket connection...")
            try:
                await self.websocket.close()
                print("Existing websocket connection closed")
            except Exception as e:
                print(f"Error closing existing websocket connection: {e}")
            finally:
                self.websocket = None
                print("Websocket reference cleared")

    async def disconnect(self):
        """Disconnect from the Webex websocket."""
        print("Disconnecting from Webex websocket...")

        # Set running to False first to signal tasks to stop
        self.running = False
        print("Set running flag to False")

        # Clean up resources
        await self._cleanup_resources()

        print("Disconnected from Webex websocket")

    async def _message_loop(self):
        """Handle incoming websocket messages using a simpler approach based on the reference implementation."""
        print("Starting message loop...")

        try:
            while self.running:
                try:
                    # Get the device info and websocket URL
                    device_info = await self._get_device_info()
                    websocket_url = device_info.get('webSocketUrl')

                    if not websocket_url:
                        print("No websocket URL found, waiting to retry...")
                        await asyncio.sleep(5)
                        continue

                    print(f"Opening websocket connection to {websocket_url}")

                    # Connect to the websocket
                    async with websockets.connect(websocket_url) as ws:
                        self.websocket = ws
                        print("WebSocket opened successfully")

                        # Send authorization message
                        token_data = get_token()
                        if not token_data:
                            print("No token data found, cannot authorize")
                            await asyncio.sleep(5)
                            continue

                        auth_msg = {
                            "id": str(uuid.uuid4()),
                            "type": "authorization",
                            "data": {"token": "Bearer " + token_data['access_token']}
                        }

                        print("Sending authorization message...")
                        await ws.send(json.dumps(auth_msg))
                        print("Authorization message sent")

                        # Reset reconnection count on successful connection
                        self.reset_reconnection_count()

                        # Process messages
                        while self.running:
                            try:
                                print("Waiting for websocket message...")
                                message = await ws.recv()
                                print(f"Received websocket message: {message[:100]}...")  # Print first 100 chars

                                # Process the message in the current task
                                await self._process_message(message)
                            except websockets.exceptions.ConnectionClosed as e:
                                print(f"Websocket connection closed: {e}")
                                break
                            except asyncio.CancelledError:
                                print("Message processing cancelled")
                                raise
                            except Exception as e:
                                print(f"Error processing message: {e}")
                                # Continue to next message

                except asyncio.CancelledError:
                    print("Message loop cancelled, exiting")
                    raise
                except Exception as e:
                    print(f"Error in websocket connection: {e}")

                    # Increment reconnection count
                    self.reconnection_count += 1
                    print(f"Reconnection attempt {self.reconnection_count}/{self.max_reconnection_count}")

                    if self.reconnection_count >= self.max_reconnection_count:
                        print(f"Maximum reconnection attempts ({self.max_reconnection_count}) reached, giving up")
                        break

                    # Wait before retrying
                    retry_delay = min(30, 2 ** self.reconnection_count)
                    print(f"Waiting {retry_delay} seconds before reconnecting...")

                    try:
                        await asyncio.sleep(retry_delay)
                    except asyncio.CancelledError:
                        print("Reconnection sleep cancelled")
                        raise

                # Clear websocket reference
                self.websocket = None

        except asyncio.CancelledError:
            print("Message loop task cancelled, exiting gracefully")
            raise
        except Exception as e:
            print(f"Unexpected error in message loop: {e}")
        finally:
            print("Message loop exiting")
            # Clear websocket reference
            self.websocket = None

    async def _process_message(self, message_str: str):
        """Process a websocket message."""
        try:
            # Parse the message
            print("Parsing message...")
            data = json.loads(message_str)
            print(f"Message parsed successfully. Data type: {type(data)}, Keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")

            # Handle the message
            await self._handle_message(data)
        except Exception as e:
            print(f"Error processing message: {e}")

    async def _handle_message(self, data: Dict):
        """Handle a websocket message."""
        # Debug: Print the received data structure
        print(f"Received websocket data: {json.dumps(data, indent=2)}")

        # Check if this is an activity event
        event_type = data.get('data', {}).get('eventType')
        print(f"Event type: {event_type}")

        if event_type == 'conversation.activity':
            activity = data['data']['activity']
            print(f"Activity received: {json.dumps(activity, indent=2)}")

            # Check if this is a message event - accept both 'post' and 'share' verbs
            verb = activity.get('verb')
            print(f"Verb: {verb}, Has message_callback: {self.message_callback is not None}")

            if verb in ['post', 'share'] and self.message_callback:
                # Get the message details - use the ID from the activity
                message_id = activity.get('id')
                print(f"Message ID from activity: {message_id}")

                # Try different locations for the room ID
                room_id = activity.get('target', {}).get('id')
                print(f"Room ID from target: {room_id}")

                if not room_id:
                    # Try to get room ID from the 'object' field if available
                    room_id = activity.get('object', {}).get('roomId')
                    print(f"Room ID from object: {room_id}")

                print(f"Message event detected - ID: {message_id}, Room: {room_id}, Current room: {self.current_room_id}")

                # Only process messages for the current room and if we have a valid message ID
                if room_id == self.current_room_id and message_id:
                    print(f"Processing message for current room: {room_id}")
                    try:
                        # Get the full message details - convert UUID to Hydra ID first
                        print(f"Getting message details for ID: {message_id}")
                        hydra_id = self.build_hydra_id(message_id)
                        print(f"Converted to Hydra ID: {hydra_id}")
                        message = self.client.get_message(hydra_id)
                        print(f"Retrieved message: {json.dumps(message, indent=2)}")

                        # Call the callback with the message
                        print(f"Calling message_callback with message: {message.get('text', '')}")
                        await self.message_callback(message)
                        print("Message callback completed")

                    except WebexAPIError as e:
                        print(f"Error getting message details: {e}")
                elif not message_id:
                    print(f"Warning: No message ID found in activity data")
                elif room_id != self.current_room_id:
                    print(f"Ignoring message for different room: {room_id}, Current room: {self.current_room_id}")

    def set_room(self, room_id: str):
        """Set the current room to listen for messages."""
        print(f"Setting current room ID to: {room_id}")
        self.current_room_id = room_id
        print(f"Current room ID set to: {room_id}")

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
        print(f"Setting message callback function: {callback.__name__ if hasattr(callback, '__name__') else 'anonymous function'}")
        self.message_callback = callback
        print("Message callback function set successfully")


async def create_websocket_client() -> WebexWebsocket:
    """Create and connect a websocket client."""
    print("Creating websocket client...")
    client = WebexWebsocket()
    print("Websocket client created, connecting...")

    try:
        # Yield control back to the event loop before connecting
        await asyncio.sleep(0)

        success = await client.connect()
        if not success:
            raise Exception("Failed to connect to Webex websocket")

        print("Websocket client connected successfully")

        # Yield control back to the event loop after connecting
        await asyncio.sleep(0)

        return client
    except Exception as e:
        print(f"Error creating websocket client: {e}")
        # Make sure to clean up resources if connection fails
        try:
            await client.disconnect()
            print("Cleaned up resources after connection failure")
        except Exception as cleanup_error:
            print(f"Error cleaning up resources: {cleanup_error}")
        # Re-raise the original exception
        raise
