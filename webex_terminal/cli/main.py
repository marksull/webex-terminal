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
                    # Extract the command part (without the /) but preserve case for parameters
                    command_with_args = text[1:]
                    # Get the command part in lowercase for case-insensitive command matching
                    command_parts = command_with_args.split(maxsplit=1)
                    command = command_parts[0].lower()

                    if command == "exit":
                        exit_event.set()
                        break
                    elif command == "help":
                        print("\nAvailable commands:")
                        print("  /exit - Exit the room")
                        print("  /help - Show this help message")
                        print("  /rooms - List all rooms")
                        print("  /members - List all members in the current room")
                        print("  /detail - Display details about the current room")
                        print("  /join <room_id> - Join another room")
                        print(
                            "  /files - List all files in the current room with their IDs"
                        )
                        print(
                            "  /attach <filename> - Upload a file to the current room"
                        )
                        print(
                            "  /download <filename> - Download a file from the current room (can use filename or ID)"
                        )
                        print(
                            "  /nn - Show the last nn messages in the room (where nn is a number between 1 and 10)"
                        )
                    elif command == "rooms":
                        # Use the display_rooms function with print output
                        # since we're in an async context
                        display_rooms(client, use_print=True)
                    elif command == "members":
                        # List all members in the current room
                        try:
                            from texttable import Texttable

                            # Get room members
                            members = client.list_room_members(room["id"])

                            if not members:
                                print("\nNo members found in this room.")
                            else:
                                # Create a table
                                table = Texttable()
                                table.set_deco(Texttable.HEADER)
                                table.set_cols_align(["l", "l", "l", "c"])
                                table.set_cols_width([30, 30, 20, 10])

                                # Add header row
                                table.add_row(
                                    ["Display Name", "Email", "Created", "Moderator"]
                                )

                                # Add member rows
                                for member in members:
                                    # Get person details
                                    person_id = member.get("personId", "")
                                    display_name = member.get(
                                        "personDisplayName", "Unknown"
                                    )
                                    email = member.get("personEmail", "Unknown")
                                    created = member.get("created", "Unknown")
                                    is_moderator = (
                                        "Yes"
                                        if member.get("isModerator", False)
                                        else "No"
                                    )

                                    # Format created date (if available)
                                    if created != "Unknown":
                                        # Just take the date part (first 10 characters)
                                        created = created[:10]

                                    # Add row to table
                                    table.add_row(
                                        [display_name, email, created, is_moderator]
                                    )

                                # Print the table
                                print(f"\nMembers in room '{room['title']}':")
                                print(table.draw())
                        except ImportError:
                            print(
                                "\nError: texttable module not found. Please install it with 'pip install texttable'."
                            )
                        except WebexAPIError as e:
                            print(f"\nError retrieving room members: {e}")
                    elif command == "detail":
                        # Display details about the current room
                        try:
                            # Get the latest room details
                            room_details = client.get_room(room["id"])

                            # Get room members count
                            members = client.list_room_members(room["id"])
                            member_count = len(members)

                            # Print room details
                            print("\nRoom Details:")
                            print(f"  Title: {room_details.get('title', 'Unknown')}")
                            print(f"  ID: {room_details.get('id', 'Unknown')}")
                            print(
                                f"  Type: {room_details.get('type', 'Unknown').capitalize()}"
                            )

                            # Format and display creation date if available
                            created = room_details.get("created", "Unknown")
                            if created != "Unknown":
                                # Just take the date part (first 10 characters)
                                created = created[:10]
                            print(f"  Created: {created}")

                            # Display last activity if available
                            last_activity = room_details.get("lastActivity", "Unknown")
                            if last_activity != "Unknown":
                                # Just take the date part (first 10 characters)
                                last_activity = last_activity[:10]
                            print(f"  Last Activity: {last_activity}")

                            # Display team info if available
                            if "teamId" in room_details:
                                print(
                                    f"  Team ID: {room_details.get('teamId', 'Unknown')}"
                                )

                            # Display member count
                            print(f"  Member Count: {member_count}")

                            # Display if the room is locked
                            is_locked = (
                                "Yes" if room_details.get("isLocked", False) else "No"
                            )
                            print(f"  Locked: {is_locked}")

                        except WebexAPIError as e:
                            print(f"\nError retrieving room details: {e}")
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
                    elif command == "join" and len(command_parts) > 1:
                        # Exit current room and join new one
                        # Use the original case for the room ID
                        new_room_id = command_parts[1].strip()
                        try:
                            new_room = client.get_room(new_room_id)
                            exit_event.set()
                            break
                        except WebexAPIError as e:
                            print(f"Error joining room: {e}")
                    elif command == "attach" and len(command_parts) > 1:
                        # Upload a file to the current room
                        file_path = command_parts[1].strip()
                        if not file_path:
                            print("Error: Please specify a filename to attach.")
                        else:
                            try:
                                # Try to upload the file
                                response = client.create_message_with_file(
                                    room["id"], file_path
                                )
                                print(
                                    f"File '{os.path.basename(file_path)}' uploaded successfully."
                                )
                            except FileNotFoundError:
                                print(f"Error: File not found: {file_path}")
                            except WebexAPIError as e:
                                print(f"Error uploading file: {e}")
                            except Exception as e:
                                print(f"Unexpected error uploading file: {e}")
                    elif command == "download" and len(command_parts) > 1:
                        # Download a file from the current room
                        filename = command_parts[1].strip()
                        if not filename:
                            print("Error: Please specify a filename to download.")
                        else:
                            try:
                                # Try to download the file
                                save_path = client.download_file(room["id"], filename)
                                print(
                                    f"File '{filename}' downloaded successfully to '{save_path}'."
                                )
                            except FileNotFoundError:
                                print(f"Error: File not found in room: {filename}")
                            except WebexAPIError as e:
                                print(f"Error downloading file: {e}")
                            except Exception as e:
                                print(f"Unexpected error downloading file: {e}")
                    elif command == "files":
                        # List all files in the current room
                        try:
                            # Get files in the room
                            files = client.list_files(room["id"])

                            if not files:
                                print("\nNo files found in this room.")
                            else:
                                # Create a table to display files
                                try:
                                    from texttable import Texttable

                                    # Create a table
                                    table = Texttable()
                                    table.set_deco(Texttable.HEADER)
                                    table.set_cols_align(["l", "l", "l", "l", "l"])
                                    table.set_cols_width([30, 15, 10, 15, 10])

                                    # Add header row
                                    table.add_row(["Filename", "Type", "Size", "Created", "ID"])

                                    # Add file rows
                                    for file_info in files:
                                        # Get file details
                                        file_id = file_info.get("id", "")
                                        filename = file_info.get("filename", "")
                                        content_type = file_info.get("contentType", "")

                                        # Format content type to be more readable
                                        if content_type:
                                            # Extract the main type (e.g., "application/pdf" -> "pdf")
                                            content_type_parts = content_type.split("/")
                                            if len(content_type_parts) > 1:
                                                content_type = content_type_parts[1].upper()
                                            else:
                                                content_type = content_type_parts[0].upper()

                                        # Format file size to be more readable
                                        size = file_info.get("size", 0)
                                        if size:
                                            # Convert to KB, MB, etc.
                                            if size < 1024:
                                                size_str = f"{size} B"
                                            elif size < 1024 * 1024:
                                                size_str = f"{size / 1024:.1f} KB"
                                            elif size < 1024 * 1024 * 1024:
                                                size_str = f"{size / (1024 * 1024):.1f} MB"
                                            else:
                                                size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
                                        else:
                                            size_str = ""

                                        # Format created date to be more readable
                                        created = file_info.get("created", "")
                                        if created:
                                            # Just take the date part (first 10 characters)
                                            created = created[:10]

                                        # Add row to table
                                        table.add_row([filename, content_type, size_str, created, file_id])

                                    # Print the table
                                    print(f"\nFiles in room '{room['title']}':")
                                    print(table.draw())
                                    print(
                                        "\nUse /download <filename> to download a file. You can use either the filename or the ID."
                                    )
                                except ImportError:
                                    # If texttable is not available, use simple formatting
                                    print(f"\nFiles in room '{room['title']}':")
                                    print("--------------------")
                                    print(
                                        "Filename                          Type        Size        Created         ID"
                                    )
                                    print(
                                        "--------------------              --------    --------    ------------    --------------------"
                                    )
                                    for file_info in files:
                                        # Get file details
                                        file_id = file_info.get("id", "")
                                        filename = file_info.get("filename", "")
                                        content_type = file_info.get("contentType", "")

                                        # Format content type to be more readable
                                        if content_type:
                                            # Extract the main type (e.g., "application/pdf" -> "pdf")
                                            content_type_parts = content_type.split("/")
                                            if len(content_type_parts) > 1:
                                                content_type = content_type_parts[1].upper()
                                            else:
                                                content_type = content_type_parts[0].upper()

                                        # Format file size to be more readable
                                        size = file_info.get("size", 0)
                                        if size:
                                            # Convert to KB, MB, etc.
                                            if size < 1024:
                                                size_str = f"{size} B"
                                            elif size < 1024 * 1024:
                                                size_str = f"{size / 1024:.1f} KB"
                                            elif size < 1024 * 1024 * 1024:
                                                size_str = f"{size / (1024 * 1024):.1f} MB"
                                            else:
                                                size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
                                        else:
                                            size_str = ""

                                        # Format created date to be more readable
                                        created = file_info.get("created", "")
                                        if created:
                                            # Just take the date part (first 10 characters)
                                            created = created[:10]

                                        # Print file info
                                        print(
                                            f"  {filename:<30} {content_type:<10} {size_str:<10} {created:<12} {file_id}"
                                        )
                                    print(
                                        "\nUse /download <filename> to download a file. You can use either the filename or the ID."
                                    )
                        except WebexAPIError as e:
                            print(f"\nError retrieving files: {e}")
                        except Exception as e:
                            print(f"\nUnexpected error retrieving files: {e}")
                    else:
                        # If the text starts with a slash, it's an unknown command
                        if text.startswith("/"):
                            print(f"Error: Unknown command '{text}'")
                        # Otherwise, send the message to the room
                        elif text.strip():
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
