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
    """Enum for Hydra message types.

    This enum defines the different types of messages that can be sent or received
    through the Webex Hydra API.

    Attributes:
        MESSAGE: Represents a standard message.
        ATTACHMENT_ACTION: Represents an action on an attachment.
    """
    MESSAGE = "MESSAGE"
    ATTACHMENT_ACTION = "ATTACHMENT_ACTION"


class WebexWebsocket:
    """Websocket client for Webex events.

    This class provides a websocket connection to the Webex API for receiving
    real-time events such as new messages. It handles authentication, connection
    management, and message processing.

    Attributes:
        client (WebexClient): An authenticated Webex API client.
        websocket: The websocket connection.
        device_info (dict): Information about the registered device.
        running (bool): Whether the websocket is currently running.
        message_callback: Callback function for new messages.
        current_room_id (str): ID of the room to listen for messages.
        reconnection_count (int): Number of reconnection attempts.
        max_reconnection_count (int): Maximum number of reconnection attempts.
        HYDRA_PREFIX (str): Prefix for Hydra IDs.
        last_error: The last error encountered.
    """

    def __init__(self):
        """Initialize the websocket client.

        This method initializes the WebexWebsocket instance by setting up the
        necessary attributes with default values.

        Returns:
            None
        """
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
        self.last_error = None

    def reset_reconnection_count(self):
        """Reset the reconnection counter.

        This method resets the reconnection counter to zero, which is used to track
        the number of reconnection attempts made.

        Returns:
            None
        """
        self.reconnection_count = 0

    async def _register_device(self) -> Dict:
        """Register a device with Webex to receive websocket events.

        This asynchronous method registers a new device with the Webex API, which is
        required to establish a websocket connection for receiving real-time events.

        Returns:
            Dict: Information about the registered device.

        Raises:
            Exception: If there's an error during device registration.
        """
        try:
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
            print(f"Registering device with Webex...")
            response = requests.post(url, headers=headers, json=data)

            # Check for HTTP errors
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                # Get more details from the response if available
                error_msg = str(e)
                try:
                    error_json = response.json()
                    if 'message' in error_json:
                        error_msg = f"{error_msg} - {error_json['message']}"
                except:
                    pass

                print(f"Device registration failed: {error_msg}")
                # Store the error and re-raise
                self.last_error = e
                raise

            result = response.json()
            self.device_info = result
            print("Device registration successful")
            return result

        except Exception as e:
            # Store the error for reference
            self.last_error = e
            print(f"Device registration error: {e.__class__.__name__}: {str(e)}")
            # Re-raise the exception
            raise

    async def _get_device_info(self) -> Dict:
        """Get the device info, registering a new device if necessary.

        This asynchronous method retrieves the device information needed for
        establishing a websocket connection. If no device is registered yet,
        it will register a new one.

        Returns:
            Dict: Information about the registered device.

        Raises:
            Exception: If there's an error during device registration.
        """
        # Register a device if we don't have one
        if not self.device_info:
            await self._register_device()

        return self.device_info

    async def connect(self):
        """Connect to the Webex websocket.

        This asynchronous method establishes a connection to the Webex websocket
        service, which allows receiving real-time events.

        Returns:
            bool: True if the connection was successful, False otherwise.

        Raises:
            Exception: If there's an error during connection.
        """
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
            # Print detailed error information for debugging
            print(f"Websocket connection error: {e.__class__.__name__}: {str(e)}")
            # Store the last error for reference
            self.last_error = e
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
                except Exception as e:
                    # Store the error for reference
                    self.last_error = e

                    # Print detailed error information for debugging
                    print(f"Websocket message loop error: {e.__class__.__name__}: {str(e)}")

                    # Increment reconnection count
                    self.reconnection_count += 1

                    if self.reconnection_count >= self.max_reconnection_count:
                        print(f"Maximum reconnection attempts ({self.max_reconnection_count}) reached. Giving up.")
                        print(f"Last error: {e.__class__.__name__}: {str(e)}")
                        break

                    # Wait before retrying
                    retry_delay = min(30, 2 ** self.reconnection_count)
                    print(f"Reconnecting in {retry_delay} seconds (attempt {self.reconnection_count}/{self.max_reconnection_count})...")

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
        """Set the current room to listen for messages.

        This method sets the ID of the room for which the websocket should
        listen for new messages.

        Args:
            room_id (str): The ID of the room to listen for messages.

        Returns:
            None
        """
        self.current_room_id = room_id

    def build_hydra_id(self, uuid, message_type=HydraTypes.MESSAGE.value):
        """Convert a UUID into Hydra ID that includes geo routing.

        This method takes a UUID and converts it into a Hydra ID format that
        includes geographic routing information.

        Args:
            uuid (str): The UUID to be encoded.
            message_type (str, optional): The type of message to be encoded.
                Defaults to HydraTypes.MESSAGE.value.

        Returns:
            str: The encoded UUID in Hydra ID format.
        """
        return (
            base64.b64encode(f"{self.HYDRA_PREFIX}/{message_type}/{uuid}".encode("ascii")).decode(
                "ascii"
            )
            if "-" in uuid
            else uuid
        )

    def on_message(self, callback: Callable[[Dict], Any]):
        """Set the callback for new messages.

        This method sets the callback function that will be called when a new
        message is received from the websocket.

        Args:
            callback (Callable[[Dict], Any]): The callback function to be called
                with the message data when a new message is received.

        Returns:
            None
        """
        self.message_callback = callback


async def create_websocket_client() -> WebexWebsocket:
    """Create and connect a websocket client.

    This asynchronous function creates a new WebexWebsocket instance and
    establishes a connection to the Webex websocket service.

    Returns:
        WebexWebsocket: A connected websocket client.

    Raises:
        Exception: If there's an error during connection.
    """
    client = WebexWebsocket()

    try:
        # Yield control back to the event loop before connecting
        await asyncio.sleep(0)

        success = await client.connect()
        if not success:
            # Check if we have a specific error stored
            if hasattr(client, 'last_error') and client.last_error:
                error_details = f"{client.last_error.__class__.__name__}: {str(client.last_error)}"
                raise Exception(f"Failed to connect to Webex websocket: {error_details}")
            else:
                raise Exception("Failed to connect to Webex websocket. Please check your network connection and authentication.")

        # Yield control back to the event loop after connecting
        await asyncio.sleep(0)

        return client
    except Exception as e:
        # Make sure to clean up resources if connection fails
        try:
            await client.disconnect()
        except Exception:
            pass

        # Re-raise with more detailed error information
        if str(e).startswith("Failed to connect to Webex websocket"):
            # This is already our detailed error, just re-raise it
            raise
        else:
            # This is some other error, include the details
            raise Exception(f"Failed to connect to Webex websocket: {str(e)}")
