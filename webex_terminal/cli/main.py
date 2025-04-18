"""
Main CLI entry point for Webex Terminal.
"""
import os
import sys
import asyncio
import click
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

from webex_terminal.auth.auth import authenticate, is_authenticated, logout
from webex_terminal.api.client import WebexClient, WebexAPIError
from webex_terminal.api.websocket import WebexWebsocket, create_websocket_client


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
    
    # Set the current room
    websocket.set_room(room['id'])
    
    # Get user info
    me = client.get_me()
    
    # Create prompt session
    session = PromptSession()
    
    # Print welcome message
    print(f"\nJoined room: {room['title']}")
    print("Type a message and press Enter to send. Type /help for available commands.")
    
    # Define message callback
    async def message_callback(message):
        # Skip messages from self
        if message.get('personId') == me['id']:
            return
        
        # Get sender info
        try:
            sender = client.get_person(message['personId'])
            sender_name = sender.get('displayName', 'Unknown')
        except:
            sender_name = 'Unknown'
        
        # Print the message
        with patch_stdout():
            print(HTML(f"\n<username>{sender_name}</username>: <message>{message.get('text', '')}</message>"))
    
    # Set message callback
    websocket.on_message(message_callback)
    
    # Message loop
    try:
        while True:
            with patch_stdout():
                text = await session.prompt_async(HTML(f"<username>{me['displayName']}</username>@<room>{room['title']}</room>> "), style=style)
            
            # Handle commands
            if text.startswith('/'):
                command = text[1:].lower()
                
                if command == 'exit':
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
                        await websocket.disconnect()
                        return await room_session(new_room)
                    except WebexAPIError as e:
                        print(f"Error joining room: {e}")
                else:
                    print(f"Unknown command: {command}")
            else:
                # Send message
                if text.strip():
                    try:
                        client.create_message(room['id'], text)
                    except WebexAPIError as e:
                        print(f"Error sending message: {e}")
    
    finally:
        # Disconnect websocket
        await websocket.disconnect()


def main():
    """Main entry point."""
    try:
        cli()
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()