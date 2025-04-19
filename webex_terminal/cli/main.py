"""
Main CLI entry point for Webex Terminal.
"""
import os
import sys
import json
import asyncio
import click
import markdown
import html
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit import print_formatted_text
from prompt_toolkit.key_binding import KeyBindings

from webex_terminal.auth.auth import authenticate, is_authenticated, logout
from webex_terminal.api.client import WebexClient, WebexAPIError
from webex_terminal.api.new_websocket import create_websocket_client


def display_rooms(client, use_print=False):
    """Display a list of available Webex rooms.

    This function retrieves and displays a list of Webex rooms that the user
    has access to. It handles the case where no rooms are found.

    Args:
        client (WebexClient): An authenticated Webex API client
        use_print (bool): If True, use print() instead of click.echo()

    Returns:
        list: The list of rooms, or None if no rooms were found
    """
    rooms = client.list_rooms()

    if not rooms:
        if use_print:
            print("No rooms found.")
        else:
            click.echo("No rooms found.")
        return None

    # Display rooms
    if use_print:
        print("\nAvailable rooms:")
        print("----------------")
        for i, room in enumerate(rooms, 1):
            print(f"{i}. {room['title']} (ID: {room['id']})")
    else:
        click.echo("\nAvailable rooms:")
        click.echo("----------------")
        for i, room in enumerate(rooms, 1):
            click.echo(f"{i}. {room['title']} (ID: {room['id']})")

    return rooms


# Prompt toolkit style
style = Style.from_dict(
    {
        "username": "#44ff44 bold",
        "room": "#4444ff bold",
        "message": "#ffffff",
        "system": "#ff4444 italic",
    }
)


@click.group()
def cli():
    """Webex Terminal - A terminal client for Cisco Webex.

    This function serves as the main command group for the CLI application.
    All subcommands are attached to this group.
    """
    pass


@cli.command()
def auth():
    """Authenticate with Webex.

    This function handles the authentication process with Webex.
    It checks for existing authentication, retrieves client credentials
    from environment variables, and initiates the authentication flow.

    Environment variables required:
        WEBEX_CLIENT_ID: The client ID from Webex Developer Portal
        WEBEX_CLIENT_SECRET: The client secret from Webex Developer Portal

    Returns:
        None
    """
    # Check if already authenticated
    if is_authenticated():
        click.echo("Already authenticated. Use 'logout' to clear credentials.")
        return

    # Get client credentials from environment variables
    client_id = os.environ.get("WEBEX_CLIENT_ID")
    client_secret = os.environ.get("WEBEX_CLIENT_SECRET")

    if not client_id or not client_secret:
        click.echo(
            "Error: WEBEX_CLIENT_ID and WEBEX_CLIENT_SECRET environment variables must be set."
        )
        click.echo(
            "You can obtain these from the Webex Developer Portal: https://developer.webex.com/my-apps"
        )
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
    """Log out from Webex.

    This function clears the stored authentication credentials,
    effectively logging the user out of Webex.

    Returns:
        None
    """
    logout()
    click.echo("Logged out successfully.")


@cli.command()
def list_rooms():
    """List available Webex rooms.

    This function retrieves and displays all Webex rooms that the
    authenticated user has access to. It requires authentication
    before it can be used.

    Returns:
        None

    Raises:
        SystemExit: If the user is not authenticated or if there's an API error
    """
    # Check if authenticated
    if not is_authenticated():
        click.echo("Not authenticated. Please run 'webex-terminal auth' first.")
        sys.exit(1)

    try:
        # Get rooms
        client = WebexClient()
        rooms = display_rooms(client)

        if not rooms:
            return

        click.echo()

    except WebexAPIError as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument("room_id", required=False)
@click.option("--name", "-n", help="Room name to join")
def join_room(room_id, name):
    """Join a Webex room by ID or name.

    This function allows the user to join a specific Webex room either by its ID
    or by its name. If neither room_id nor name is provided, it displays a list
    of available rooms and prompts the user to select one.

    Args:
        room_id (str, optional): The ID of the room to join.
        name (str, optional): The name of the room to join.

    Returns:
        None

    Raises:
        SystemExit: If the user is not authenticated, if the room cannot be found,
                   or if there's an API error
    """
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
            room_id = room["id"]

        # If no room ID or name provided, show list of rooms
        if not room_id:
            rooms = display_rooms(client)

            if not rooms:
                return

            # Prompt for room selection
            selection = click.prompt("Enter room number to join", type=int)
            if selection < 1 or selection > len(rooms):
                click.echo("Invalid selection.")
                sys.exit(1)

            room_id = rooms[selection - 1]["id"]

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
    """Interactive room session.

    This asynchronous function creates an interactive session for a Webex room.
    It sets up a websocket connection to receive real-time messages, handles user
    input, and manages the display of messages in the terminal.

    Args:
        room (dict): A dictionary containing room information, including 'id' and 'title'.

    Returns:
        None: If the session ends normally
        Awaitable: If switching to a new room, returns an awaitable for the new room session

    Raises:
        Exception: If there's an error during the room session
    """
    client = WebexClient()
    websocket = await create_websocket_client()

    # Set the current room - prefer globalId if available, otherwise use id
    room_id = room.get("globalId", room["id"])
    websocket.set_room(room_id)

    # Get user info
    me = client.get_me()

    # Create custom key bindings
    kb = KeyBindings()

    # Make Enter add a new line, but submit if it's a command
    @kb.add("enter")
    def _(event):
        """Handle Enter key press in the prompt.

        This function determines the behavior when the Enter key is pressed.
        If the current text starts with '/', it's treated as a command and submitted.
        Otherwise, a new line is added to the input buffer.

        Args:
            event: The key press event object containing the current buffer.

        Returns:
            None
        """
        buffer = event.current_buffer
        text = buffer.text

        # If the input starts with '/', treat it as a command and submit
        if text.startswith("/"):
            buffer.validate_and_handle()
        else:
            buffer.newline()

    @kb.add("escape", "enter")
    def _(event):
        """Handle Escape+Enter key combination in the prompt.

        This function handles the behavior when Escape followed by Enter is pressed.
        It validates and submits the current input buffer content.

        Args:
            event: The key press event object containing the current buffer.

        Returns:
            None
        """
        event.current_buffer.validate_and_handle()

    send_key_desc = "Escape followed by Enter"

    session = PromptSession(multiline=True, key_bindings=kb)

    print(f"\nJoined room: {room['title']}")
    print(
        f"Type a message and press Enter to add a new line. Press {send_key_desc} to send. Type /help for available commands."
    )

    # Create an event to signal when to exit the room
    exit_event = asyncio.Event()
    new_room = None

    # Define message callback
    async def message_callback(message):
        """Process incoming messages from the websocket.

        This asynchronous function handles incoming messages from the Webex websocket.
        It skips messages from the current user, retrieves sender information,
        and displays the message in the terminal with appropriate formatting.

        Args:
            message (dict): The message object received from the websocket.

        Returns:
            None
        """
        # Skip messages from self
        if message.get("personId") == me["id"]:
            return

        # Get sender info
        # noinspection PyBroadException
        try:
            sender = client.get_person(message["personId"])
            sender_name = sender.get("displayName", "Unknown")
        except Exception:
            sender_name = "Unknown"

        # Print the message
        # Use markdown content if available, otherwise fall back to text
        message_text = message.get("markdown", message.get("text", ""))
        # noinspection PyBroadException
        try:
            # Yield control back to the event loop before displaying the message
            await asyncio.sleep(0)

            # Convert markdown to HTML if markdown content is available
            if message.get("markdown"):
                # Escape any HTML in the original message to prevent injection
                safe_text = html.escape(message_text)
                # Convert markdown to HTML
                html_content = markdown.markdown(safe_text)
                # Remove surrounding <p> tags if they exist
                html_content = html_content.strip()
                if html_content.startswith("<p>") and html_content.endswith("</p>"):
                    html_content = html_content[3:-4]
            else:
                # If no markdown, just escape the text
                html_content = html.escape(message_text)

            with patch_stdout():
                # Format message with sender name as prefix, keeping the styling
                print_formatted_text(
                    HTML(
                        f"\n<username>{sender_name}</username>: <message>{html_content}</message>"
                    ),
                    style=style,
                )
                # Redisplay the prompt after the message
                print_formatted_text(
                    HTML(
                        f"<username>{me['displayName']}</username>@<room>{room['title']}</room>> "
                    ),
                    style=style,
                    end="",
                )

            # Yield control back to the event loop after displaying the message
            await asyncio.sleep(0)
        except Exception:
            pass

    # Set message callback
    websocket.on_message(message_callback)

    # Function to handle user input
    async def handle_user_input():
        """Handle user input in the interactive room session.

        This asynchronous function manages the user input loop for the room session.
        It captures user input, processes commands (prefixed with '/'), and sends
        messages to the Webex room. It also handles room switching and session exit.

        Returns:
            None
        """
        nonlocal new_room

        # noinspection PyBroadException
        try:
            while not exit_event.is_set():
                try:
                    # Yield control back to the event loop before getting user input
                    await asyncio.sleep(0)

                    with patch_stdout():
                        text = await session.prompt_async(
                            HTML(
                                f"<username>{me['displayName']}</username>@<room>{room['title']}</room>> "
                            ),
                            style=style,
                        )

                    # Yield control back to the event loop after getting user input
                    await asyncio.sleep(0)
                except (EOFError, KeyboardInterrupt):
                    exit_event.set()
                    break

                # Handle commands
                if text.startswith("/"):
                    command = text[1:].lower()

                    if command == "exit":
                        exit_event.set()
                        break
                    elif command == "help":
                        print("\nAvailable commands:")
                        print("  /exit - Exit the room")
                        print("  /help - Show this help message")
                        print("  /list - List all rooms")
                        print("  /join <room_id> - Join another room")
                        print(
                            "  /nn - Show the last nn messages in the room (where nn is a number between 1 and 10)"
                        )
                    elif command == "list":
                        # Use the display_rooms function with print output
                        # since we're in an async context
                        display_rooms(client, use_print=True)
                    elif command.isdigit() and 1 <= int(command) <= 10:
                        # Retrieve and display the last n messages in the room
                        num_messages = int(command)
                        try:
                            messages = client.list_messages(
                                room["id"], max_results=num_messages
                            )
                            if not messages:
                                print("\nNo messages found in this room.")
                            else:
                                print(f"\nLast {num_messages} messages:")
                                # Messages are returned in reverse chronological order (newest first)
                                # Display them in chronological order (oldest first)
                                for message in reversed(messages):
                                    # Skip messages without text
                                    if "text" not in message:
                                        continue

                                    # Get sender info
                                    try:
                                        sender = client.get_person(message["personId"])
                                        sender_name = sender.get(
                                            "displayName", "Unknown"
                                        )
                                    except Exception:
                                        sender_name = "Unknown"

                                    # Format and print the message
                                    # Use markdown content if available, otherwise fall back to text
                                    message_text = message.get(
                                        "markdown", message.get("text", "")
                                    )
                                    with patch_stdout():
                                        print_formatted_text(
                                            HTML(
                                                f"<username>{sender_name}</username>: <message>{message_text}</message>"
                                            ),
                                            style=style,
                                        )
                        except WebexAPIError as e:
                            print(f"Error retrieving messages: {e}")
                    elif command.startswith("join "):
                        # Exit current room and join new one
                        new_room_id = command[5:].strip()
                        try:
                            new_room = client.get_room(new_room_id)
                            exit_event.set()
                            break
                        except WebexAPIError as e:
                            print(f"Error joining room: {e}")
                else:
                    if text.strip():
                        try:
                            # Pass the text as both plain text and markdown
                            # The API will use markdown if it contains valid markdown
                            response = client.create_message(
                                room["id"], text, markdown=text
                            )
                        except WebexAPIError as e:
                            print(f"Error sending message: {e}")
        except Exception:
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
            # noinspection PyBroadException
            try:
                await websocket.disconnect()
            except Exception:
                pass


def main():
    """Main entry point for the Webex Terminal application.

    This function serves as the entry point for the application when run from
    the command line. It calls the CLI command group and handles any exceptions
    that might occur during execution.

    Returns:
        None

    Raises:
        SystemExit: If an unhandled exception occurs during execution
    """
    try:
        cli()
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
