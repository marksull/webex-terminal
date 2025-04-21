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
import shutil
import subprocess
import platform
import tempfile
import imghdr
import re
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit import print_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from texttable import Texttable

from webex_terminal.auth.auth import (
    authenticate,
    is_authenticated,
    logout as auth_logout,
)
from webex_terminal.api.client import WebexClient, WebexAPIError
from webex_terminal.api.new_websocket import create_websocket_client
from webex_terminal.config import load_config, save_config


def display_image_in_terminal(image_path):
    """Display an image in the terminal.

    This function attempts to display an image directly in the terminal using
    the appropriate method for the current operating system and terminal.

    Args:
        image_path (str): Path to the image file to display.

    Returns:
        bool: True if the image was displayed successfully, False otherwise.
    """
    system = platform.system()

    try:
        if system == "Darwin":  # macOS
            # Check if running in iTerm2
            if "ITERM_SESSION_ID" in os.environ:
                # Use imgcat for iTerm2
                subprocess.run(["imgcat", image_path], check=True)
                return True
            else:
                # For Terminal.app, open the image in the default viewer
                subprocess.run(["open", image_path], check=True)
                print(f"Image opened in default viewer: {image_path}")
                return True
        elif system == "Linux":
            # Try using display from ImageMagick
            try:
                subprocess.run(["display", image_path], check=True)
                return True
            except (subprocess.SubprocessError, FileNotFoundError):
                # If display is not available, try xdg-open
                try:
                    subprocess.run(["xdg-open", image_path], check=True)
                    print(f"Image opened in default viewer: {image_path}")
                    return True
                except (subprocess.SubprocessError, FileNotFoundError):
                    print(f"Unable to display image. Image saved at: {image_path}")
                    return False
        elif system == "Windows":
            # On Windows, open the image in the default viewer
            os.startfile(image_path)
            print(f"Image opened in default viewer: {image_path}")
            return True
        else:
            print(f"Unsupported operating system. Image saved at: {image_path}")
            return False
    except Exception as e:
        print(f"Error displaying image: {e}")
        print(f"Image saved at: {image_path}")
        return False


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
    auth_logout()
    click.echo("Logged out successfully.")


@cli.command()
@click.argument("filter_text", required=False)
def list_rooms(filter_text):
    """List available Webex rooms.

    This function retrieves and displays all Webex rooms that the
    authenticated user has access to. It requires authentication
    before it can be used.

    Args:
        filter_text (str, optional): Text to filter rooms by. Only rooms with titles
                                    containing this text will be displayed.

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

        # Get all rooms
        rooms = client.list_rooms()

        if not rooms:
            click.echo("No rooms found.")
            return

        # Filter rooms if filter_text is provided
        if filter_text:
            filtered_rooms = [
                room for room in rooms if filter_text.lower() in room["title"].lower()
            ]

            if not filtered_rooms:
                click.echo(f"No rooms found matching '{filter_text}'.")
                return

            # Display filtered rooms
            click.echo(f"\nRooms matching '{filter_text}':")
            click.echo("----------------")
            for i, room in enumerate(filtered_rooms, 1):
                click.echo(f"{i}. {room['title']} (ID: {room['id']})")
        else:
            # No filter, display all rooms using the display_rooms function
            display_rooms(client)

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
    except Exception as e:
        # Handle other exceptions, including websocket connection errors
        if "Failed to connect to Webex websocket" in str(e):
            click.echo(f"Error: {e}")
            click.echo("\nTroubleshooting tips:")
            click.echo("1. Check your internet connection")
            click.echo(
                "2. Verify your authentication by running 'webex-terminal auth' again"
            )
            click.echo("3. Check if Webex services are experiencing any outages")
            click.echo("4. Try again in a few minutes")
        else:
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

    # Debug mode flag - controls whether to display message payload for debugging
    debug_mode = False

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

    # Automatically display room details (same as /details command)
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
        print(f"  Type: {room_details.get('type', 'Unknown').capitalize()}")

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
            print(f"  Team ID: {room_details.get('teamId', 'Unknown')}")

        # Display member count
        print(f"  Member Count: {member_count}")

        # Display if the room is locked
        is_locked = "Yes" if room_details.get("isLocked", False) else "No"
        print(f"  Locked: {is_locked}")

    except WebexAPIError as e:
        print(f"\nError retrieving room details: {e}")

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

            # Check for file attachments
            file_info = ""
            if "files" in message:
                file_info = "\n[Attachments]:"

                # Process each file attachment
                for file_url in message.get("files", []):
                    file_info += f"\n- {file_url}"

                    # Try to download and display image attachments
                    try:
                        # Download the file
                        file_path = client.download_file_from_url(file_url)

                        # Check if it's an image file based on extension or content type
                        image_extensions = [
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".gif",
                            ".bmp",
                            ".webp",
                        ]
                        is_image = any(
                            file_path.lower().endswith(ext) for ext in image_extensions
                        )

                        # If we couldn't determine from extension, try to check the file content
                        if not is_image:
                            import imghdr

                            img_type = imghdr.what(file_path)
                            is_image = img_type is not None

                        # If it's an image, display it
                        if is_image:
                            # Display the image
                            display_image_in_terminal(file_path)
                    except Exception as e:
                        file_info += f"\n  Error processing attachment: {e}"

                # Add debug information if debug mode is enabled
                if debug_mode:
                    file_info += (
                        f"\n\n[Debug] Message payload: {json.dumps(message, indent=2)}"
                    )

            with patch_stdout():
                # Load config to check if sound is enabled
                config = load_config()

                # Play bell sound if enabled
                if config.get("sound_enabled", True):
                    print("\a", end="", flush=True)  # \a is the ASCII bell character

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
        except Exception as e:
            # Print the exception for debugging
            print(f"\nError processing message: {e}")
            pass

    # Set message callback
    websocket.on_message(message_callback)

    # Helper methods for handling commands
    async def handle_exit_command():
        """Handle the /exit command.

        This function sets the exit event to signal that the user wants to exit
        the current room session.

        Returns:
            bool: True to indicate the command was handled and the session should exit.
        """
        exit_event.set()
        return True

    async def handle_help_command():
        """Handle the /help command.

        This function displays a list of all available commands and their descriptions
        to help the user navigate the application.

        Returns:
            bool: False to indicate the session should continue.
        """
        print("\nAvailable commands:")
        print("  /exit - Exit the room")
        print("  /help - Show this help message")
        print("  /rooms [filter] - List all rooms, optionally filtered by text")
        print("  /teams [filter] - List all teams that you are a member of, optionally filtered by text")
        print("  /spaces <team> - List all spaces in the specified team")
        print("  /members - List all members in the current room")
        print("  /add <email_address> - Add a user to the current room")
        print("  /details - Display details about the current room")
        print("  /join <room_id or name> - Join another room by ID, exact name, or partial name")
        print("  /files - List all files in the current room with their IDs")
        print("  /links - List all links shared in the current room")
        print("  /urls - List all tabs (URLs) associated with the current room")
        print("  /upload <filename> - Upload a file to the current room")
        print(
            "  /download <filename> - Download a file from the current room (can use filename or ID)"
        )
        print(
            "  /open <filename> - Download and open a file from the current room with the default application"
        )
        print("  /delete - Delete the last message you sent in the room")
        print("  /debug - Toggle debug mode to show/hide message payloads")
        print("  /sound - Toggle notification sound for new messages")
        print("  /logout - Log out from Webex by deleting the token file")
        print(
            "  /nn - Show the last nn messages in the room (where nn is a number between 1 and 10)"
        )
        print(
            "\nTo send a message that starts with a slash, prefix it with another slash:"
        )
        print("  //hello - Sends the message '/hello' to the room")
        return False

    async def handle_rooms_command(command_parts):
        """Handle the /rooms command.

        This function lists all available Webex rooms, optionally filtered by text.

        Args:
            command_parts (list): The command split into parts, where command_parts[1]
                                 may contain filter text if provided.

        Returns:
            bool: False to indicate the session should continue.
        """
        # Check if there's additional text to filter rooms
        filter_text = ""
        if len(command_parts) > 1:
            filter_text = command_parts[1].strip().lower()

        # Get all rooms
        rooms = client.list_rooms()

        if not rooms:
            print("No rooms found.")
            return False

        # Filter rooms if filter_text is provided
        if filter_text:
            filtered_rooms = [r for r in rooms if filter_text in r["title"].lower()]

            if not filtered_rooms:
                print(f"\nNo rooms found matching '{filter_text}'.")
                return False

            # Display filtered rooms
            print(f"\nRooms matching '{filter_text}':")
            print("----------------")
            for i, r in enumerate(filtered_rooms, 1):
                print(f"{i}. {r['title']} (ID: {r['id']})")
        else:
            # No filter, display all rooms
            print("\nAvailable rooms:")
            print("----------------")
            for i, r in enumerate(rooms, 1):
                print(f"{i}. {r['title']} (ID: {r['id']})")
        return False

    async def handle_spaces_command(command_parts):
        """Handle the /spaces command.

        This function lists all spaces (rooms) in a specific Webex team.

        Args:
            command_parts (list): The command split into parts, where command_parts[1]
                                 contains the team name or ID.

        Returns:
            bool: False to indicate the session should continue.
        """
        # Check if team name/ID is provided
        if len(command_parts) < 2:
            print("Error: Team name or ID is required.")
            print("Usage: /spaces <team name or ID>")
            return False

        team_identifier = command_parts[1].strip()

        # Get all teams
        teams = client.list_teams()

        if not teams:
            print("No teams found.")
            return False

        # Find the team by name or ID
        target_team = None
        for team in teams:
            # Check for exact ID match
            if team["id"] == team_identifier:
                target_team = team
                break
            # Check for case-insensitive name match
            elif team["name"].lower() == team_identifier.lower():
                target_team = team
                break

        # If no exact match, try partial name match
        if not target_team:
            matching_teams = [t for t in teams if team_identifier.lower() in t["name"].lower()]
            if len(matching_teams) == 1:
                target_team = matching_teams[0]
            elif len(matching_teams) > 1:
                print(f"\nMultiple teams match '{team_identifier}':")
                for i, t in enumerate(matching_teams, 1):
                    print(f"{i}. {t['name']} (ID: {t['id']})")
                print("\nPlease use a more specific team name or the team ID.")
                return False

        if not target_team:
            print(f"No team found matching '{team_identifier}'.")
            return False

        # Get spaces (rooms) for the team
        spaces = client.list_team_rooms(target_team["id"])

        if not spaces:
            print(f"No spaces found in team '{target_team['name']}'.")
            return False

        # Display spaces
        print(f"\nSpaces in team '{target_team['name']}':")
        print("----------------")
        for i, space in enumerate(spaces, 1):
            print(f"{i}. {space['title']} (ID: {space['id']})")

        return False

    async def handle_teams_command(command_parts):
        """Handle the /teams command.

        This function lists all Webex teams that the user is a member of,
        optionally filtered by text.

        Args:
            command_parts (list): The command split into parts, where command_parts[1]
                                 may contain filter text if provided.

        Returns:
            bool: False to indicate the session should continue.
        """
        # Check if there's additional text to filter teams
        filter_text = ""
        if len(command_parts) > 1:
            filter_text = command_parts[1].strip().lower()

        # Get all teams
        teams = client.list_teams()

        if not teams:
            print("No teams found.")
            return False

        # Filter teams if filter_text is provided
        if filter_text:
            filtered_teams = [t for t in teams if filter_text in t["name"].lower()]

            if not filtered_teams:
                print(f"\nNo teams found matching '{filter_text}'.")
                return False

            # Display filtered teams
            print(f"\nTeams matching '{filter_text}':")
            print("----------------")
            for i, t in enumerate(filtered_teams, 1):
                print(f"{i}. {t['name']} (ID: {t['id']})")
        else:
            # No filter, display all teams
            print("\nAvailable teams:")
            print("----------------")
            for i, t in enumerate(teams, 1):
                print(f"{i}. {t['name']} (ID: {t['id']})")
        return False

    async def handle_members_command():
        """Handle the /members command.

        This function retrieves and displays a list of all members in the current room,
        including their display names, email addresses, when they joined, and whether
        they are moderators.

        Returns:
            bool: False to indicate the session should continue.

        Raises:
            ImportError: If the texttable module is not installed.
            WebexAPIError: If there's an error retrieving members from the API.
        """
        try:
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
                table.add_row(["Display Name", "Email", "Created", "Moderator"])

                # Add member rows
                for member in members:
                    # Get person details
                    person_id = member.get("personId", "")
                    display_name = member.get("personDisplayName", "Unknown")
                    email = member.get("personEmail", "Unknown")
                    created = member.get("created", "Unknown")
                    is_moderator = "Yes" if member.get("isModerator", False) else "No"

                    # Format created date (if available)
                    if created != "Unknown":
                        # Just take the date part (first 10 characters)
                        created = created[:10]

                    # Add row to table
                    table.add_row([display_name, email, created, is_moderator])

                # Print the table
                print(f"\nMembers in room '{room['title']}':")
                print(table.draw())
        except ImportError:
            print(
                "\nError: texttable module not found. Please install it with 'pip install texttable'."
            )
        except WebexAPIError as e:
            print(f"\nError retrieving room members: {e}")
        return False

    async def handle_details_command():
        """Handle the /details command.

        This function retrieves and displays detailed information about the current room,
        including its title, ID, type, creation date, last activity, team ID (if applicable),
        member count, and whether it's locked.

        Returns:
            bool: False to indicate the session should continue.

        Raises:
            WebexAPIError: If there's an error retrieving room details from the API.
        """
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
            print(f"  Type: {room_details.get('type', 'Unknown').capitalize()}")

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
                print(f"  Team ID: {room_details.get('teamId', 'Unknown')}")

            # Display member count
            print(f"  Member Count: {member_count}")

            # Display if the room is locked
            is_locked = "Yes" if room_details.get("isLocked", False) else "No"
            print(f"  Locked: {is_locked}")

        except WebexAPIError as e:
            print(f"\nError retrieving room details: {e}")
        return False

    async def handle_numeric_command(command):
        """Handle numeric commands for retrieving messages."""
        num_messages = int(command)
        try:
            messages = client.list_messages(room["id"], max_results=num_messages)
            if not messages:
                print("\nNo messages found in this room.")
            else:
                print(f"\nLast {num_messages} messages:")
                # Messages are returned in reverse chronological order (newest first)
                # Display them in chronological order (oldest first)
                for message in reversed(messages):
                    # Skip messages without text or files
                    if "text" not in message and "files" not in message:
                        continue

                    # Get sender info
                    try:
                        sender = client.get_person(message["personId"])
                        sender_name = sender.get("displayName", "Unknown")
                    except Exception:
                        sender_name = "Unknown"

                    # Format and print the message
                    # Use markdown content if available, otherwise fall back to text
                    message_text = message.get("markdown", message.get("text", ""))

                    # Convert markdown to HTML if markdown content is available
                    if message.get("markdown"):
                        # Escape any HTML in the original message to prevent injection
                        safe_text = html.escape(message_text)
                        # Convert markdown to HTML
                        html_content = markdown.markdown(safe_text)
                        # Remove surrounding <p> tags if they exist
                        html_content = html_content.strip()
                        if html_content.startswith("<p>") and html_content.endswith(
                            "</p>"
                        ):
                            html_content = html_content[3:-4]
                    else:
                        # If no markdown, just escape the text
                        html_content = html.escape(message_text)

                    # Prepare file info before displaying the message
                    file_info = ""
                    file_paths = []
                    is_image_list = []

                    # Check for file attachments
                    if "files" in message:
                        file_info = "[Attachments]:"

                        # Process each file attachment
                        for file_url in message.get("files", []):
                            file_info += f"\n- {file_url}"

                            # Try to download and display image attachments
                            try:
                                # Download the file
                                file_path = client.download_file_from_url(file_url)
                                file_paths.append(file_path)

                                # Check if it's an image file based on extension or content type
                                image_extensions = [
                                    ".jpg",
                                    ".jpeg",
                                    ".png",
                                    ".gif",
                                    ".bmp",
                                    ".webp",
                                ]
                                is_image = any(
                                    file_path.lower().endswith(ext)
                                    for ext in image_extensions
                                )

                                # If we couldn't determine from extension, try to check the file content
                                if not is_image:
                                    img_type = imghdr.what(file_path)
                                    is_image = img_type is not None

                                is_image_list.append(is_image)
                            except Exception as e:
                                file_info += f"\n  Error processing attachment: {e}"
                                file_paths.append(None)
                                is_image_list.append(False)

                    # Add debug information if debug mode is enabled
                    if debug_mode:
                        file_info += f"\n\n[Debug] Message payload: {json.dumps(message, indent=2)}"

                    # Display the message
                    with patch_stdout():
                        print_formatted_text(
                            HTML(
                                f"<username>{sender_name}</username>: <message>{html_content}</message>"
                            ),
                            style=style,
                        )

                        for i, file_path in enumerate(file_paths):
                            if file_path and is_image_list[i]:
                                # Display the image
                                display_image_in_terminal(file_path)
        except WebexAPIError as e:
            print(f"Error retrieving messages: {e}")
        return False

    async def handle_add_command(command_parts):
        """Handle the /add command.

        This function adds a user to the current room using their email address.

        Args:
            command_parts (list): The command split into parts, where command_parts[1]
                                 contains the email address of the user to add.

        Returns:
            bool: False to indicate the session should continue.
        """
        if len(command_parts) <= 1:
            print("Error: Please specify an email address to add.")
            print("Usage: /add <email_address>")
            return False

        email = command_parts[1].strip()
        if not email:
            print("Error: Please specify an email address to add.")
            return False

        try:
            # Add the user to the room
            response = client.add_user_to_room(room["id"], email)
            print(f"User with email '{email}' has been added to the room.")
        except WebexAPIError as e:
            print(f"Error adding user to room: {e}")
        return False

    async def handle_join_command(command_parts):
        """Handle the /join command.

        The command accepts a room ID, exact room name, or partial room name.
        If multiple rooms match the partial name, a list of matching rooms is displayed
        for the user to choose from.
        """
        nonlocal room
        if len(command_parts) <= 1:
            print("Error: Please specify a room ID or name to join.")
            return False

        # Use the original case for the room ID or name
        room_identifier = command_parts[1].strip()

        # First try to get the room by ID
        try:
            temp_room = client.get_room(room_identifier)

            # Set the new room ID on the existing websocket client
            room_id = temp_room.get("globalId", temp_room["id"])
            websocket.set_room(room_id)

            # Update the room variable to the new room
            room = temp_room

            # Print a message indicating the room change
            print(f"Joined room: {temp_room['title']}")

            # No need to exit the current room session
            return False
        except WebexAPIError:
            # If room ID doesn't exist, try to find by name
            pass

        # Try to find room by exact name
        temp_room = client.get_room_by_name(room_identifier)
        if temp_room:
            # Set the new room ID on the existing websocket client
            room_id = temp_room.get("globalId", temp_room["id"])
            websocket.set_room(room_id)

            # Update the room variable to the new room
            room = temp_room

            # Print a message indicating the room change
            print(f"Joined room: {temp_room['title']}")

            # No need to exit the current room session
            return False

        # Try to find rooms by partial name
        matching_rooms = client.search_rooms_by_name(room_identifier)
        if not matching_rooms:
            print(f"No rooms found matching '{room_identifier}'.")
            return False

        if len(matching_rooms) == 1:
            # Only one match, join it directly
            temp_room = matching_rooms[0]

            # Set the new room ID on the existing websocket client
            room_id = temp_room.get("globalId", temp_room["id"])
            websocket.set_room(room_id)

            # Update the room variable to the new room
            room = temp_room

            # Print a message indicating the room change
            print(f"Joined room: {temp_room['title']}")

            # No need to exit the current room session
            return False

        # Multiple matches, display them and let the user choose
        print(f"Multiple rooms match '{room_identifier}':")
        for i, r in enumerate(matching_rooms, 1):
            print(f"{i}. {r['title']}")

        try:
            selection = input("Enter room number to join (or press Enter to cancel): ")
            if not selection:
                return False

            selection_index = int(selection) - 1
            if selection_index < 0 or selection_index >= len(matching_rooms):
                print("Invalid selection.")
                return False

            temp_room = matching_rooms[selection_index]

            # Set the new room ID on the existing websocket client
            room_id = temp_room.get("globalId", temp_room["id"])
            websocket.set_room(room_id)

            # Update the room variable to the new room
            room = temp_room

            # Print a message indicating the room change
            print(f"Joined room: {temp_room['title']}")
        except ValueError:
            print("Invalid selection.")
        except Exception as e:
            print(f"Error joining room: {e}")

        return False

    async def handle_upload_command(command_parts):
        """Handle the /upload command."""
        if len(command_parts) <= 1:
            print("Error: Please specify a filename to upload.")
            return False

        file_path = command_parts[1].strip()
        if not file_path:
            print("Error: Please specify a filename to upload.")
        else:
            try:
                # Try to upload the file
                response = client.create_message_with_file(room["id"], file_path)
                print(f"File '{os.path.basename(file_path)}' uploaded successfully.")
            except FileNotFoundError:
                print(f"Error: File not found: {file_path}")
            except WebexAPIError as e:
                print(f"Error uploading file: {e}")
            except Exception as e:
                print(f"Unexpected error uploading file: {e}")
        return False

    async def handle_download_command(command_parts):
        """Handle the /download command."""
        if len(command_parts) <= 1:
            print("Error: Please specify a filename to download.")
            return False

        filename = command_parts[1].strip()
        if not filename:
            print("Error: Please specify a filename to download.")
        else:
            try:
                # Try to download the file
                save_path = client.download_file(room["id"], filename)
                print(f"File '{filename}' downloaded successfully to '{save_path}'.")
            except FileNotFoundError:
                print(f"Error: File not found in room: {filename}")
            except WebexAPIError as e:
                print(f"Error downloading file: {e}")
            except Exception as e:
                print(f"Unexpected error downloading file: {e}")
        return False

    async def handle_open_command(command_parts):
        """Handle the /open command."""
        if len(command_parts) <= 1:
            print("Error: Please specify a filename to open.")
            return False

        filename = command_parts[1].strip()
        if not filename:
            print("Error: Please specify a filename to open.")
        else:
            try:
                # Try to download the file
                save_path = client.download_file(room["id"], filename)
                print(f"File '{filename}' downloaded successfully to '{save_path}'.")

                # Open the file with the default application based on the platform
                try:
                    if platform.system() == "Windows":
                        os.startfile(save_path)
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.run(["open", save_path], check=True)
                    else:  # Linux and other Unix-like systems
                        subprocess.run(["xdg-open", save_path], check=True)
                    print(f"Opened file '{save_path}' with the default application.")
                except Exception as e:
                    print(f"Error opening file: {e}")

            except FileNotFoundError:
                print(f"Error: File not found in room: {filename}")
            except WebexAPIError as e:
                print(f"Error downloading file: {e}")
            except Exception as e:
                print(f"Unexpected error downloading file: {e}")
        return False

    async def handle_remove_command(command_parts):
        """Handle the /remove command.

        This function removes a user from the current room using their email address.

        Args:
            command_parts (list): The command split into parts, where command_parts[1]
                                 contains the email address of the user to remove.

        Returns:
            bool: False to indicate the session should continue.
        """
        if len(command_parts) <= 1:
            print("Error: Please specify an email address to remove.")
            print("Usage: /remove <email_address>")
            return False

        email = command_parts[1].strip()
        if not email:
            print("Error: Please specify an email address to remove.")
            return False

        try:
            # Remove the user from the room
            client.remove_user_from_room(room["id"], email)
            print(f"User with email '{email}' has been removed from the room.")
        except WebexAPIError as e:
            print(f"Error removing user from room: {e}")
        return False

    async def handle_delete_command(command_parts=None):
        """Handle the /delete command.

        This function deletes the last message sent by the current user in the room.

        Args:
            command_parts (list, optional): Not used, kept for compatibility.

        Returns:
            bool: False to indicate the session should continue.
        """
        try:
            # Get the last few messages in the room
            messages = client.list_messages(room["id"], max_results=20)

            # Find the last message sent by the current user
            last_message = None
            for message in messages:
                if message.get("personId") == me["id"]:
                    last_message = message
                    break

            if last_message:
                # Delete the message
                client.delete_message(last_message["id"])
                print("Last message deleted successfully.")
            else:
                print("No recent messages found from you in this room.")
        except WebexAPIError as e:
            print(f"Error deleting message: {e}")
        return False

    async def handle_files_command():
        """Handle the /files command."""
        try:
            # Get files in the room
            files = client.list_files(room["id"])

            if not files:
                print("\nNo files found in this room.")
            else:
                # Create a table to display files
                try:
                    # Get terminal width
                    terminal_width = shutil.get_terminal_size().columns

                    # Calculate column widths based on terminal width
                    # Use proportions: filename (30%), type (15%), size (10%), created (15%), ID (30%)
                    # Ensure minimum width of 80 characters to avoid errors on very small terminals
                    effective_width = max(
                        terminal_width - 5, 80
                    )  # Subtract 5 for table borders and padding

                    filename_width = int(effective_width * 0.30)
                    type_width = int(effective_width * 0.15)
                    size_width = int(effective_width * 0.10)
                    created_width = int(effective_width * 0.15)
                    id_width = (
                        effective_width
                        - filename_width
                        - type_width
                        - size_width
                        - created_width
                    )

                    # Create a table
                    table = Texttable(max_width=terminal_width)
                    table.set_deco(Texttable.HEADER)
                    table.set_cols_align(["l", "l", "l", "l", "l"])
                    table.set_cols_width(
                        [
                            filename_width,
                            type_width,
                            size_width,
                            created_width,
                            id_width,
                        ]
                    )

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
                        table.add_row(
                            [filename, content_type, size_str, created, file_id]
                        )

                    # Print the table
                    print(f"\nFiles in room '{room['title']}':")
                    print(table.draw())
                    print(
                        "\nUse /download <filename> to download a file or /open <filename> to download and open it."
                    )
                    print(
                        "You can use either the filename or the ID for both commands."
                    )
                except ImportError:
                    # If texttable is not available, use simple formatting
                    # Get terminal width
                    terminal_width = shutil.get_terminal_size().columns

                    # Calculate column widths based on terminal width
                    # Use proportions: filename (30%), type (15%), size (10%), created (15%), ID (30%)
                    # Ensure minimum width of 80 characters to avoid errors on very small terminals
                    effective_width = max(terminal_width, 80)

                    filename_width = int(effective_width * 0.30)
                    type_width = int(effective_width * 0.15)
                    size_width = int(effective_width * 0.10)
                    created_width = int(effective_width * 0.15)
                    id_width = (
                        effective_width
                        - filename_width
                        - type_width
                        - size_width
                        - created_width
                    )

                    print(f"\nFiles in room '{room['title']}':")
                    print("-" * terminal_width)

                    # Create header format string with dynamic widths
                    header_format = f"{{:<{filename_width}}} {{:<{type_width}}} {{:<{size_width}}} {{:<{created_width}}} {{:<{id_width}}}"
                    print(
                        header_format.format(
                            "Filename", "Type", "Size", "Created", "ID"
                        )
                    )

                    # Create a separator line with dynamic widths
                    separator_format = f"{{:-<{filename_width}}} {{:-<{type_width}}} {{:-<{size_width}}} {{:-<{created_width}}} {{:-<{id_width}}}"
                    print(separator_format.format("", "", "", "", ""))
                    for file_info in files:
                        # Get file details
                        file_id = file_info.get("id", "")
                        filename = file_info.get("filename", "")
                        content_type = file_info.get("contentType", "")

                        # Format content types to be more readable
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

                        # Print file info using the dynamic format
                        print(
                            header_format.format(
                                filename, content_type, size_str, created, file_id
                            )
                        )
                    print(
                        "\nUse /download <filename> to download a file or /open <filename> to download and open it."
                    )
                    print(
                        "You can use either the filename or the ID for both commands."
                    )
        except WebexAPIError as e:
            print(f"\nError retrieving files: {e}")
        except Exception as e:
            print(f"\nUnexpected error retrieving files: {e}")
        return False

    async def handle_debug_command():
        """Handle the /debug command.

        This function toggles the debug mode, which controls whether message payloads
        are displayed for debugging purposes.

        Returns:
            bool: False to indicate the session should continue.
        """
        nonlocal debug_mode
        # Toggle debug mode
        debug_mode = not debug_mode

        # Provide feedback to the user
        if debug_mode:
            print("\nDebug mode enabled. Message payloads will be displayed.")
        else:
            print("\nDebug mode disabled. Message payloads will not be displayed.")
        return False

    async def handle_sound_command():
        """Handle the /sound command.

        This function toggles the sound setting, which controls whether a bell sound
        is played when new messages are received.
        """
        # Load current config
        config = load_config()

        # Toggle sound enabled setting
        config["sound_enabled"] = not config.get("sound_enabled", True)

        # Save updated config
        save_config(config)

        # Provide feedback to the user
        if config["sound_enabled"]:
            print(
                "\nSound notifications enabled. A bell sound will play when new messages are received."
            )
        else:
            print(
                "\nSound notifications disabled. No sound will play when new messages are received."
            )

        return False

    async def handle_urls_command():
        """Handle the /urls command.

        This function retrieves all tabs (URLs) associated with the current room
        and displays them in a formatted table.

        Returns:
            bool: False to indicate the session should continue.
        """
        try:
            # Get tabs from the room
            tabs = client.list_room_tabs(room["id"])

            if not tabs:
                print("\nNo tabs (URLs) found in this room.")
                return False

            # Display the tabs
            # Create a table to display tabs
            try:
                # Get terminal width
                terminal_width = shutil.get_terminal_size().columns

                # Calculate column widths based on terminal width
                # Use proportions: Name (30%), URL (70%)
                # Ensure minimum width of 80 characters
                effective_width = max(terminal_width - 5, 80)  # Subtract 5 for table borders and padding

                name_width = int(effective_width * 0.30)
                url_width = effective_width - name_width

                # Create a table
                table = Texttable(max_width=terminal_width)
                table.set_deco(Texttable.HEADER)
                table.set_cols_align(["l", "l"])
                table.set_cols_width([name_width, url_width])

                # Add header row
                table.add_row(["Name", "URL"])

                # Add tab rows
                for tab in tabs:
                    # Try different field names for the tab name
                    tab_name = tab.get("displayName", tab.get("title", tab.get("name", "Unnamed")))
                    table.add_row([tab_name, tab.get("contentUrl", "")])

                # Print the table
                print(f"\nTabs (URLs) in room '{room['title']}' ({len(tabs)} found):")
                print(table.draw())

            except ImportError:
                # If texttable is not available, use simple formatting
                print(f"\nTabs (URLs) in room '{room['title']}' ({len(tabs)} found):")
                print("-" * terminal_width)

                # Create header format string with dynamic widths
                header_format = f"{{:<{name_width}}} {{:<{url_width}}}"
                print(header_format.format("Name", "URL"))

                # Create a separator line
                separator_format = f"{{:-<{name_width}}} {{:-<{url_width}}}"
                print(separator_format.format("", ""))

                # Print each tab
                for tab in tabs:
                    # Truncate URL if it's too long for display
                    url = tab.get("contentUrl", "")
                    if len(url) > url_width:
                        url = url[:url_width-3] + "..."

                    # Try different field names for the tab name
                    tab_name = tab.get("displayName", tab.get("title", tab.get("name", "Unnamed")))
                    if len(tab_name) > name_width:
                        tab_name = tab_name[:name_width-3] + "..."

                    print(header_format.format(tab_name, url))

        except WebexAPIError as e:
            print(f"\nError retrieving tabs: {e}")

        return False

    async def handle_links_command():
        """Handle the /links command.

        This function retrieves messages from the current room, extracts links from them,
        and displays the links in a formatted way with information about who shared them.

        Returns:
            bool: False to indicate the session should continue.
        """
        try:
            # Get messages from the room (use a higher limit to find more links)
            messages = client.list_messages(room["id"], max_results=100)

            if not messages:
                print("\nNo messages found in this room.")
                return False

            # Regular expression to find URLs in text
            url_pattern = re.compile(r'https?://\S+')

            # List to store found links
            links = []

            # Process each message to extract links
            for message in messages:
                # Skip messages without text
                if "text" not in message and "markdown" not in message:
                    continue

                # Get sender info
                try:
                    sender = client.get_person(message["personId"])
                    sender_name = sender.get("displayName", "Unknown")
                except Exception:
                    sender_name = "Unknown"

                # Get message text (prefer markdown if available)
                message_text = message.get("markdown", message.get("text", ""))

                # Find all URLs in the message text
                found_urls = url_pattern.findall(message_text)

                # Add each URL to the links list with metadata
                for url in found_urls:
                    # Get created date in a readable format
                    created = message.get("created", "Unknown")
                    if created != "Unknown":
                        # Just take the date part (first 10 characters)
                        created = created[:10]

                    links.append({
                        "url": url,
                        "sender": sender_name,
                        "created": created,
                        "message_id": message.get("id", "")
                    })

            # Display the links
            if not links:
                print("\nNo links found in this room.")
            else:
                # Create a table to display links
                try:
                    # Get terminal width
                    terminal_width = shutil.get_terminal_size().columns

                    # Calculate column widths based on terminal width
                    # Use proportions: URL (60%), Sender (25%), Date (15%)
                    # Ensure minimum width of 80 characters
                    effective_width = max(terminal_width - 5, 80)  # Subtract 5 for table borders and padding

                    url_width = int(effective_width * 0.60)
                    sender_width = int(effective_width * 0.25)
                    date_width = effective_width - url_width - sender_width

                    # Create a table
                    table = Texttable(max_width=terminal_width)
                    table.set_deco(Texttable.HEADER)
                    table.set_cols_align(["l", "l", "l"])
                    table.set_cols_width([url_width, sender_width, date_width])

                    # Add header row
                    table.add_row(["URL", "Shared By", "Date"])

                    # Add link rows
                    for link in links:
                        table.add_row([link["url"], link["sender"], link["created"]])

                    # Print the table
                    print(f"\nLinks in room '{room['title']}' ({len(links)} found):")
                    print(table.draw())

                except ImportError:
                    # If texttable is not available, use simple formatting
                    print(f"\nLinks in room '{room['title']}' ({len(links)} found):")
                    print("-" * terminal_width)

                    # Create header format string with dynamic widths
                    header_format = f"{{:<{url_width}}} {{:<{sender_width}}} {{:<{date_width}}}"
                    print(header_format.format("URL", "Shared By", "Date"))

                    # Create a separator line
                    separator_format = f"{{:-<{url_width}}} {{:-<{sender_width}}} {{:-<{date_width}}}"
                    print(separator_format.format("", "", ""))

                    # Print each link
                    for link in links:
                        # Truncate URL if it's too long for display
                        url = link["url"]
                        if len(url) > url_width:
                            url = url[:url_width-3] + "..."

                        print(header_format.format(url, link["sender"], link["created"]))

        except WebexAPIError as e:
            print(f"\nError retrieving messages: {e}")
        except Exception as e:
            print(f"\nUnexpected error: {e}")

        return False

    async def handle_logout_command():
        """Handle the /logout command.

        This function logs the user out by deleting the token file.
        """
        # Call the logout function from auth module
        from webex_terminal.auth.auth import logout as auth_logout

        auth_logout()

        # Provide feedback to the user
        print("\nLogged out successfully. Token file has been deleted.")

        # Set the exit event to exit the room session
        exit_event.set()
        return True

    async def handle_slash_message(text):
        """Handle messages that start with a slash."""
        # Check if it's a message that starts with a slash (e.g., "//" or "/text")
        if text.startswith("//"):
            # Remove the first slash and send the rest as a message
            message_text = text[1:]
            try:
                # Pass the text as both plain text and markdown
                # The API will use markdown if it contains valid markdown
                response = client.create_message(
                    room["id"], message_text, markdown=message_text
                )
            except WebexAPIError as e:
                print(f"Error sending message: {e}")
        else:
            print(f"Error: Unknown command '{text}'")
        return False

    async def handle_regular_message(text):
        """Handle regular messages (not commands)."""
        if text.strip():
            try:
                # Pass the text as both plain text and markdown
                # The API will use markdown if it contains valid markdown
                response = client.create_message(room["id"], text, markdown=text)
            except WebexAPIError as e:
                print(f"Error sending message: {e}")
        return False

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

                    # Process commands
                    should_break = False
                    if command == "exit":
                        should_break = await handle_exit_command()
                    elif command == "help":
                        should_break = await handle_help_command()
                    elif command == "rooms":
                        should_break = await handle_rooms_command(command_parts)
                    elif command == "members":
                        should_break = await handle_members_command()
                    elif command == "add":
                        should_break = await handle_add_command(command_parts)
                    elif command == "details":
                        should_break = await handle_details_command()
                    elif command.isdigit() and 1 <= int(command) <= 10:
                        should_break = await handle_numeric_command(command)
                    elif command == "join":
                        should_break = await handle_join_command(command_parts)
                    elif command == "upload":
                        should_break = await handle_upload_command(command_parts)
                    elif command == "download":
                        should_break = await handle_download_command(command_parts)
                    elif command == "open":
                        should_break = await handle_open_command(command_parts)
                    elif command == "delete":
                        should_break = await handle_delete_command()
                    elif command == "remove":
                        should_break = await handle_remove_command(command_parts)
                    elif command == "files":
                        should_break = await handle_files_command()
                    elif command == "debug":
                        should_break = await handle_debug_command()
                    elif command == "sound":
                        should_break = await handle_sound_command()
                    elif command == "links":
                        should_break = await handle_links_command()
                    elif command == "urls":
                        should_break = await handle_urls_command()
                    elif command == "teams":
                        should_break = await handle_teams_command(command_parts)
                    elif command == "spaces":
                        should_break = await handle_spaces_command(command_parts)
                    elif command == "logout":
                        should_break = await handle_logout_command()
                    else:
                        should_break = await handle_slash_message(text)

                    if should_break:
                        break
                # Otherwise, send the message to the room
                else:
                    await handle_regular_message(text)
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
