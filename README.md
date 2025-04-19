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

### Commands

While in a room, you can use the following commands:

- `/exit` - Exit the room
- `/help` - Show this help message
- `/rooms` - List all rooms
- `/members` - List all members in the current room
- `/detail` - Display details about the current room
- `/join <room_id>` - Join another room
- `/upload <filename>` - Upload a file to the current room
- `/nn` - Show the last nn messages in the room (where nn is a number between 1 and 10)

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
