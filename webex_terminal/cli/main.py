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
from prompt_toolkit import print_formatted_text
from prompt_toolkit.key_binding import KeyBindings

from webex_terminal.auth.auth import authenticate, is_authenticated, logout
from webex_terminal.api.client import WebexClient, WebexAPIError
from webex_terminal.api.new_websocket import create_websocket_client


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
    # Check if authenticated
    if not is_authenticated():
        click.echo("Not authenticated. Please run 'webex-terminal auth' first.")
        sys.exit(1)

    try:
        client = WebexClient()

        # Get room by name if specified
        if name and not room_id:
            room = client.get_room_by_name(name)
            if not room:
                click.echo(f"Room with name '{name}' not found.")
                sys.exit(1)
            room_id = room['id']

        # If no room ID or name provided, show list of rooms
        if not room_id:
            rooms = client.list_rooms()

            if not rooms:
                click.echo("No rooms found.")
                return

            # Display rooms
            click.echo("\nAvailable rooms:")
            click.echo("----------------")
            for i, room in enumerate(rooms, 1):
                click.echo(f"{i}. {room['title']} (ID: {room['id']})")

            # Prompt for room selection
            selection = click.prompt("Enter room number to join", type=int)
            if selection < 1 or selection > len(rooms):
                click.echo("Invalid selection.")
                sys.exit(1)

            room_id = rooms[selection - 1]['id']

        # Get room details
        room = client.get_room(room_id)

        # Start the room session
        asyncio.run(room_session(room))

    except WebexAPIError as e:
        click.echo(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nExiting...")


async def room_session(room):
    """Interactive room session."""
    client = WebexClient()
    websocket = await create_websocket_client()

    # Set the current room - prefer globalId if available, otherwise use id
    room_id = room.get('globalId', room['id'])
    websocket.set_room(room_id)

    # Get user info
    me = client.get_me()

    # Create custom key bindings
    kb = KeyBindings()

    # Make Enter add a new line, but submit if it's a command
    @kb.add('enter')
    def _(event):
        buffer = event.current_buffer
        text = buffer.text

        # If the input starts with '/', treat it as a command and submit
        if text.startswith('/'):
            buffer.validate_and_handle()
        else:
            # Otherwise, add a new line
            buffer.newline()

    # Detect platform and set appropriate key binding
    if sys.platform == 'darwin':  # macOS
        # Make Command+Enter submit the input (Meta+Enter)
        @kb.add('escape', 'enter')  # Fallback for terminals that don't support meta keys
        def _(event):
            event.current_buffer.validate_and_handle()

        send_key_desc = "Command+Enter (or Escape followed by Enter as fallback)"
    else:  # Windows/Linux
        # Make Windows+Enter or Ctrl+Enter submit the input
        @kb.add('escape', 'enter')  # Fallback for all platforms
        def _(event):
            event.current_buffer.validate_and_handle()

        send_key_desc = "Windows+Enter or Ctrl+Enter (or Escape followed by Enter as fallback)"

    # Create prompt session with multiline support and custom key bindings
    session = PromptSession(multiline=True, key_bindings=kb)

    # Print welcome message
    print(f"\nJoined room: {room['title']}")
    print(f"Type a message and press Enter to add a new line. Press {send_key_desc} to send. Type /help for available commands.")

    # Create an event to signal when to exit the room
    exit_event = asyncio.Event()
    new_room = None

    # Define message callback
    async def message_callback(message):
        # Skip messages from self
        if message.get('personId') == me['id']:
            return

        # Get sender info
        try:
            sender = client.get_person(message['personId'])
            sender_name = sender.get('displayName', 'Unknown')
        except Exception:
            sender_name = 'Unknown'

        # Print the message
        message_text = message.get('text', '')
        try:
            # Yield control back to the event loop before displaying the message
            await asyncio.sleep(0)

            with patch_stdout():
                # Format message with sender name as prefix, keeping the styling
                print_formatted_text(HTML(f"\n<username>{sender_name}</username>: <message>{message_text}</message>"), style=style)
                # Redisplay the prompt after the message
                print_formatted_text(HTML(f"<username>{me['displayName']}</username>@<room>{room['title']}</room>> "), style=style, end='')

            # Yield control back to the event loop after displaying the message
            await asyncio.sleep(0)
        except Exception:
            pass

    # Set message callback
    websocket.on_message(message_callback)

    # Function to handle user input
    async def handle_user_input():
        nonlocal new_room

        try:
            while not exit_event.is_set():
                try:
                    # Yield control back to the event loop before getting user input
                    await asyncio.sleep(0)

                    with patch_stdout():
                        text = await session.prompt_async(
                            HTML(f"<username>{me['displayName']}</username>@<room>{room['title']}</room>> "), 
                            style=style
                        )

                    # Yield control back to the event loop after getting user input
                    await asyncio.sleep(0)
                except (EOFError, KeyboardInterrupt):
                    exit_event.set()
                    break

                # Handle commands
                if text.startswith('/'):
                    command = text[1:].lower()

                    if command == 'exit':
                        exit_event.set()
                        break
                    elif command == 'help':
                        print("\nAvailable commands:")
                        print("  /exit - Exit the room")
                        print("  /help - Show this help message")
                        print("  /list - List all rooms")
                        print("  /join <room_id> - Join another room")
                    elif command == 'list':
                        rooms = client.list_rooms()
                        print("\nAvailable rooms:")
                        for i, r in enumerate(rooms, 1):
                            print(f"{i}. {r['title']} (ID: {r['id']})")
                    elif command.startswith('join '):
                        # Exit current room and join new one
                        new_room_id = command[5:].strip()
                        try:
                            new_room = client.get_room(new_room_id)
                            exit_event.set()
                            break
                        except WebexAPIError as e:
                            print(f"Error joining room: {e}")
                else:
                    # Send message
                    if text.strip():
                        try:
                            response = client.create_message(room['id'], text)
                        except WebexAPIError as e:
                            print(f"Error sending message: {e}")
        except Exception as e:
            exit_event.set()

    # Start the user input handler task
    try:
        # Yield control back to the event loop before creating the user input task
        await asyncio.sleep(0)

        # Create and start the user input task
        user_input_task = asyncio.create_task(handle_user_input())

        # Yield control back to the event loop after creating the user input task
        await asyncio.sleep(0)

        # Wait for the exit event to be set
        await exit_event.wait()

        # Cancel the user input task if it's still running
        if not user_input_task.done():
            user_input_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(user_input_task), timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

        # Disconnect the websocket
        await websocket.disconnect()

        # If we're switching rooms, start a new room session
        if new_room:
            return await room_session(new_room)

    except Exception as e:
        click.echo(f"Error in room session: {e}")
    finally:
        # Ensure websocket is disconnected
        if websocket:
            try:
                await websocket.disconnect()
            except Exception:
                pass


def main():
    """Main entry point."""
    try:
        cli()
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
