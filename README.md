# Webex Terminal

A terminal client for Cisco Webex that allows you to join and interact with Webex rooms directly from your terminal.

## Features

- OAuth2 authentication with token storage for multiple sessions
- Join Webex rooms from the terminal
- One room per terminal (joining a new room stops listening to the previous one)
- Real-time message updates using websockets

## Installation

### From PyPI

```bash
pip install webex-terminal
```

### From Source

```bash
git clone https://github.com/yourusername/webex-terminal.git
cd webex-terminal
pip install -e .
```

## Usage

### Authentication

First, authenticate with Webex:

```bash
webex-terminal auth
```

This will open a browser window for OAuth2 authentication. After successful authentication, the token will be stored locally for future sessions.

### Listing Rooms

To list available rooms:

```bash
webex-terminal list-rooms
```

### Joining a Room

To join a specific room:

```bash
webex-terminal join-room <room_id>
```

or

```bash
webex-terminal join-room --name "Room Name"
```

### Sending Messages

Once in a room, you can type messages directly in the terminal. Press Enter to send.

To send a message that starts with a slash (e.g., "/hello"), prefix it with another slash (e.g., "//hello").

### Commands

While in a room, you can use the following commands:

- `/exit` - Exit the room
- `/help` - Show this help message
- `/rooms [filter]` - List all rooms, optionally filtered by text
- `/members` - List all members in the current room
- `/detail` - Display details about the current room
- `/join <room_id>` - Join another room
- `/files` - List all files in the current room with their IDs
- `/upload <filename>` - Upload a file to the current room
- `/download <filename>` - Download a file from the current room (can use filename or ID)
- `/open <filename>` - Download and open a file from the current room with the default application
- `/delete` - Delete the last message you sent in the room
- `/debug` - Toggle debug mode to show/hide message payloads
- `/sound` - Toggle notification sound for new messages
- `/logout` - Log out from Webex by deleting the token file
- `/nn` - Show the last nn messages in the room (where nn is a number between 1 and 10)

To send a message that starts with a slash, prefix it with another slash:
- `//hello` - Sends the message '/hello' to the room

## Development

### Requirements

- Python 3.7+
- Dependencies listed in requirements.txt

### Setup Development Environment

```bash
git clone https://github.com/yourusername/webex-terminal.git
cd webex-terminal
pip install -e ".[dev]"
```

## License

MIT
