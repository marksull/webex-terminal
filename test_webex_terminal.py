#!/usr/bin/env python3
"""
Test script for Webex Terminal.

This script demonstrates how to use the Webex Terminal application.
It requires the WEBEX_CLIENT_ID and WEBEX_CLIENT_SECRET environment variables to be set.

Usage:
    python test_webex_terminal.py

"""
import os
import sys
import subprocess
import time

# Check if environment variables are set
client_id = os.environ.get('WEBEX_CLIENT_ID')
client_secret = os.environ.get('WEBEX_CLIENT_SECRET')

if not client_id or not client_secret:
    print("Error: WEBEX_CLIENT_ID and WEBEX_CLIENT_SECRET environment variables must be set.")
    print("You can obtain these from the Webex Developer Portal: https://developer.webex.com/my-apps")
    sys.exit(1)

# Test authentication
print("\n=== Testing Authentication ===")
print("Running 'webex-terminal auth'...")
try:
    result = subprocess.run(["python", "-m", "webex_terminal.cli.main", "auth"], check=True)
    print("Authentication successful or already authenticated.")
except subprocess.CalledProcessError:
    print("Authentication failed. Please check your credentials and try again.")
    sys.exit(1)

# Test listing rooms
print("\n=== Testing Room Listing ===")
print("Running 'webex-terminal list-rooms'...")
try:
    result = subprocess.run(["python", "-m", "webex_terminal.cli.main", "list-rooms"], check=True)
except subprocess.CalledProcessError:
    print("Failed to list rooms. Make sure you're authenticated.")
    sys.exit(1)

# Instructions for joining a room
print("\n=== Joining a Room ===")
print("To join a room, run one of the following commands:")
print("  webex-terminal join-room <room_id>")
print("  webex-terminal join-room --name \"Room Name\"")
print("  webex-terminal join-room  # This will show a list of rooms to choose from")

print("\n=== Multiple Terminals ===")
print("You can open multiple terminal windows and join different rooms in each one.")
print("Each terminal will only listen to messages from the room it has joined.")

print("\n=== Room Commands ===")
print("Once in a room, you can use the following commands:")
print("  /exit - Exit the room")
print("  /help - Show available commands")
print("  /list - List all rooms")
print("  /join <room_id> - Join another room")

print("\nTest completed successfully!")