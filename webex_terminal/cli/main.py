"""
Main CLI entry point for Webex Terminal.
"""
import os
import sys
import json
import asyncio
import click
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

from webex_terminal.auth.auth import authenticate, is_authenticated, logout
from webex_terminal.api.client import WebexClient, WebexAPIError
from webex_terminal.api.new_websocket import WebexWebsocket, create_websocket_client


# Prompt toolkit style
style = Style.from_dict({
    'username': '#44ff44 bold',
    'room': '#4444ff bold',
    'message': '#ffffff',
    'system': '#ff4444 italic',
})


@click.group()
def cli():
    """Webex Terminal - A terminal client for Cisco Webex."""
    pass


@cli.command()
def auth():
    """Authenticate with Webex."""
    # Check if already authenticated
    if is_authenticated():
        click.echo("Already authenticated. Use 'logout' to clear credentials.")
        return

    # Get client credentials from environment variables
    client_id = os.environ.get('WEBEX_CLIENT_ID')
    client_secret = os.environ.get('WEBEX_CLIENT_SECRET')

    if not client_id or not client_secret:
        click.echo("Error: WEBEX_CLIENT_ID and WEBEX_CLIENT_SECRET environment variables must be set.")
        click.echo("You can obtain these from the Webex Developer Portal: https://developer.webex.com/my-apps")
        sys.exit(1)

    # Authenticate
    click.echo("Authenticating with Webex...")
    success, error = authenticate(client_id, client_secret)

    if success:
        click.echo("Authentication successful!")
    else:
        click.echo(f"Authentication failed: {error}")
        sys.exit(1)


@cli.command()
def logout():
    """Log out from Webex."""
    logout()
    click.echo("Logged out successfully.")


@cli.command()
def list_rooms():
    """List available Webex rooms."""
    # Check if authenticated
    if not is_authenticated():
        click.echo("Not authenticated. Please run 'webex-terminal auth' first.")
        sys.exit(1)

    try:
        # Get rooms
        client = WebexClient()
        rooms = client.list_rooms()

        if not rooms:
            click.echo("No rooms found.")
            return

        # Display rooms
        click.echo("\nAvailable rooms:")
        click.echo("----------------")
        for i, room in enumerate(rooms, 1):
            click.echo(f"{i}. {room['title']} (ID: {room['id']})")
        click.echo()

    except WebexAPIError as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument('room_id', required=False)
@click.option('--name', '-n', help='Room name to join')
def join_room(room_id, name):
    """Join a Webex room by ID or name."""
    print("Starting join_room function...")

    # Check if authenticated
    if not is_authenticated():
        print("Not authenticated, exiting")
        click.echo("Not authenticated. Please run 'webex-terminal auth' first.")
        sys.exit(1)
    print("Authentication check passed")

    try:
        print("Creating WebexClient...")
        client = WebexClient()
        print("WebexClient created successfully")

        # Get room by name if specified
        if name and not room_id:
            print(f"Getting room by name: {name}")
            room = client.get_room_by_name(name)
            if not room:
                print(f"Room with name '{name}' not found, exiting")
                click.echo(f"Room with name '{name}' not found.")
                sys.exit(1)
            room_id = room['id']
            print(f"Found room: {room['title']} (ID: {room_id})")

        # If no room ID or name provided, show list of rooms
        if not room_id:
            print("No room ID provided, listing rooms")
            rooms = client.list_rooms()

            if not rooms:
                print("No rooms found, exiting")
                click.echo("No rooms found.")
                return

            # Display rooms
            print(f"Found {len(rooms)} rooms")
            click.echo("\nAvailable rooms:")
            click.echo("----------------")
            for i, room in enumerate(rooms, 1):
                click.echo(f"{i}. {room['title']} (ID: {room['id']})")

            # Prompt for room selection
            print("Prompting for room selection")
            selection = click.prompt("Enter room number to join", type=int)
            if selection < 1 or selection > len(rooms):
                print(f"Invalid selection: {selection}, exiting")
                click.echo("Invalid selection.")
                sys.exit(1)

            room_id = rooms[selection - 1]['id']
            print(f"Selected room ID: {room_id}")

        # Get room details
        print(f"Getting details for room ID: {room_id}")
        room = client.get_room(room_id)
        print(f"Got room details: {room['title']} (ID: {room['id']})")

        # Start the room session
        print(f"Starting room session for room: {room['title']}")
        asyncio.run(room_session(room))

    except WebexAPIError as e:
        click.echo(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nExiting...")


async def room_session(room):
    """Interactive room session."""
    print(f"Starting room session for room: {room['title']} (ID: {room['id']})")

    print("Creating WebexClient...")
    client = WebexClient()
    print("WebexClient created successfully")

    print("Creating and connecting websocket client...")
    websocket = await create_websocket_client()
    print("Websocket client created and connected successfully")

    # Set the current room - prefer globalId if available, otherwise use id
    room_id = room.get('globalId', room['id'])
    print(f"Setting current room to: {room_id}")
    websocket.set_room(room_id)
    print(f"Current room set to: {room_id}")

    # Get user info
    print("Getting user info...")
    me = client.get_me()
    print(f"Got user info: {me['displayName']} (ID: {me['id']})")

    # Create prompt session
    print("Creating prompt session...")
    session = PromptSession()
    print("Prompt session created successfully")

    # Print welcome message
    print(f"\nJoined room: {room['title']}")
    print("Type a message and press Enter to send. Type /help for available commands.")

    # Create an event to signal when to exit the room
    exit_event = asyncio.Event()
    new_room = None

    # Define message callback
    async def message_callback(message):
        print(f"Message callback received: {json.dumps(message, indent=2)}")
        print(f"Message type: {type(message)}, Keys: {list(message.keys()) if isinstance(message, dict) else 'Not a dict'}")
        print(f"Message personId: {message.get('personId')}, My ID: {me['id']}")

        # Skip messages from self
        if message.get('personId') == me['id']:
            print(f"Skipping message from self (personId: {message.get('personId')})")
            return
        else:
            print(f"Message is from another user, processing...")

        # Get sender info
        try:
            print(f"Getting sender info for personId: {message.get('personId')}")
            sender = client.get_person(message['personId'])
            print(f"Sender info: {json.dumps(sender, indent=2)}")
            sender_name = sender.get('displayName', 'Unknown')
            print(f"Sender name: {sender_name}")
        except Exception as e:
            print(f"Error getting sender info: {e}")
            sender_name = 'Unknown'

        # Print the message
        message_text = message.get('text', '')
        print(f"Message text: {message_text}")
        print(f"Displaying message from {sender_name}: {message_text}")
        try:
            # Yield control back to the event loop before displaying the message
            await asyncio.sleep(0)

            with patch_stdout():
                print(HTML(f"\n<username>{sender_name}</username>: <message>{message_text}</message>"))
            print("Message displayed successfully")

            # Yield control back to the event loop after displaying the message
            await asyncio.sleep(0)
        except Exception as e:
            print(f"Error displaying message: {e}")

    # Set message callback
    print("Setting message callback...")
    websocket.on_message(message_callback)
    print("Message callback set successfully")

    # Function to handle user input
    async def handle_user_input():
        nonlocal new_room
        print("Starting user input handler...")

        try:
            while not exit_event.is_set():
                print("Waiting for user input...")
                try:
                    # Yield control back to the event loop before getting user input
                    await asyncio.sleep(0)

                    with patch_stdout():
                        text = await session.prompt_async(
                            HTML(f"<username>{me['displayName']}</username>@<room>{room['title']}</room>> "), 
                            style=style
                        )
                    print(f"User input received: {text}")

                    # Yield control back to the event loop after getting user input
                    await asyncio.sleep(0)
                except (EOFError, KeyboardInterrupt):
                    print("Input interrupted, exiting...")
                    exit_event.set()
                    break

                # Handle commands
                if text.startswith('/'):
                    command = text[1:].lower()
                    print(f"Command detected: {command}")

                    if command == 'exit':
                        print("Exit command received, setting exit event")
                        exit_event.set()
                        break
                    elif command == 'help':
                        print("Help command received, showing help")
                        print("\nAvailable commands:")
                        print("  /exit - Exit the room")
                        print("  /help - Show this help message")
                        print("  /list - List all rooms")
                        print("  /join <room_id> - Join another room")
                    elif command == 'list':
                        print("List command received, listing rooms")
                        rooms = client.list_rooms()
                        print("\nAvailable rooms:")
                        for i, r in enumerate(rooms, 1):
                            print(f"{i}. {r['title']} (ID: {r['id']})")
                    elif command.startswith('join '):
                        # Exit current room and join new one
                        new_room_id = command[5:].strip()
                        print(f"Join command received, joining room: {new_room_id}")
                        try:
                            print(f"Getting room details for: {new_room_id}")
                            new_room = client.get_room(new_room_id)
                            print(f"Room details retrieved: {new_room['title']}")
                            print("Setting exit event to switch rooms")
                            exit_event.set()
                            break
                        except WebexAPIError as e:
                            print(f"Error joining room: {e}")
                    else:
                        print(f"Unknown command: {command}")
                else:
                    # Send message
                    if text.strip():
                        print(f"Message detected: {text}")
                        try:
                            print(f"Sending message to room {room['id']}: {text}")
                            response = client.create_message(room['id'], text)
                            print(f"Message sent successfully. Response: {json.dumps(response, indent=2)}")
                        except WebexAPIError as e:
                            print(f"Error sending message: {e}")
        except Exception as e:
            print(f"Error in user input handler: {e}")
            exit_event.set()

        print("User input handler exiting")

    # Start the user input handler task
    print("Starting message loop...")
    try:
        # Yield control back to the event loop before creating the user input task
        await asyncio.sleep(0)

        # Create and start the user input task
        user_input_task = asyncio.create_task(handle_user_input())
        print("User input task created")

        # Yield control back to the event loop after creating the user input task
        await asyncio.sleep(0)

        # Wait for the exit event to be set
        await exit_event.wait()
        print("Exit event detected, cleaning up...")

        # Cancel the user input task if it's still running
        if not user_input_task.done():
            print("Cancelling user input task...")
            user_input_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(user_input_task), timeout=1.0)
                print("User input task cancelled successfully")
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception) as e:
                print(f"Error or timeout cancelling user input task: {e}")

        # Disconnect the websocket
        print("Disconnecting websocket...")
        await websocket.disconnect()
        print("Websocket disconnected")

        # If we're switching rooms, start a new room session
        if new_room:
            print(f"Switching to new room: {new_room['title']}")
            return await room_session(new_room)

    except Exception as e:
        print(f"Error in room session: {e}")
    finally:
        # Ensure websocket is disconnected
        if websocket:
            print("Ensuring websocket is disconnected...")
            try:
                await websocket.disconnect()
                print("Websocket disconnected in finally block")
            except Exception as e:
                print(f"Error disconnecting websocket in finally block: {e}")

        print("Room session completed")


def main():
    """Main entry point."""
    try:
        cli()
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
