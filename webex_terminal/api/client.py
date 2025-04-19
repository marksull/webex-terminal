"""
Webex API client for interacting with the Webex API.
"""
import requests
from typing import Dict, List, Optional, Any

from webex_terminal.auth.auth import get_token
from webex_terminal.config import load_config


class WebexAPIError(Exception):
    """Exception raised for Webex API errors."""
    pass


class WebexClient:
    """Client for interacting with the Webex API."""

    def __init__(self):
        """Initialize the Webex API client."""
        self.config = load_config()
        self.base_url = self.config['api_base_url']
        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        """Get the headers for API requests."""
        token_data = get_token()
        if not token_data:
            raise WebexAPIError("Not authenticated. Please run 'webex-terminal auth' first.")

        return {
            'Authorization': f"Bearer {token_data['access_token']}",
            'Content-Type': 'application/json',
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make a request to the Webex API."""
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()

        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        response = self.session.request(method, url, headers=headers, **kwargs)

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error: {e}"
            try:
                error_data = response.json()
                if 'message' in error_data:
                    error_msg = f"{error_msg} - {error_data['message']}"
            except:
                pass
            raise WebexAPIError(error_msg)
        except requests.exceptions.RequestException as e:
            raise WebexAPIError(f"Request Error: {e}")
        except ValueError:
            return {}

    def get_me(self) -> Dict:
        """Get information about the authenticated user."""
        return self._request('GET', 'people/me')

    def list_rooms(self, max_results: int = 100) -> List[Dict]:
        """
        List all rooms the user is a member of.

        Args:
            max_results: Maximum number of rooms to return

        Returns:
            List of room objects
        """
        params = {'max': max_results}
        response = self._request('GET', 'rooms', params=params)
        return response.get('items', [])

    def get_room(self, room_id: str) -> Dict:
        """
        Get details for a specific room.

        Args:
            room_id: ID of the room

        Returns:
            Room object
        """
        return self._request('GET', f'rooms/{room_id}')

    def get_room_by_name(self, name: str) -> Optional[Dict]:
        """
        Find a room by name.

        Args:
            name: Name of the room to find

        Returns:
            Room object or None if not found
        """
        rooms = self.list_rooms()
        for room in rooms:
            if room['title'].lower() == name.lower():
                return room
        return None

    def create_message(self, room_id: str, text: str, markdown: str = None) -> Dict:
        """
        Send a message to a room.

        Args:
            room_id: ID of the room to send the message to
            text: Message text
            markdown: Message text in markdown format (optional)

        Returns:
            Created message object
        """
        data = {
            'roomId': room_id,
            'text': text,
        }

        # Include markdown in the payload if provided
        if markdown:
            data['markdown'] = markdown

        return self._request('POST', 'messages', json=data)

    def list_messages(self, room_id: str, max_results: int = 50) -> List[Dict]:
        """
        List messages in a room.

        Args:
            room_id: ID of the room
            max_results: Maximum number of messages to return

        Returns:
            List of message objects
        """
        params = {
            'roomId': room_id,
            'max': max_results,
        }
        response = self._request('GET', 'messages', params=params)
        return response.get('items', [])

    def get_message(self, message_id: str) -> Dict:
        """
        Get details for a specific message.

        Args:
            message_id: ID of the message

        Returns:
            Message object
        """
        return self._request('GET', f'messages/{message_id}')

    def delete_message(self, message_id: str) -> None:
        """
        Delete a message.

        Args:
            message_id: ID of the message to delete
        """
        self._request('DELETE', f'messages/{message_id}')

    def list_people(self, email: Optional[str] = None, display_name: Optional[str] = None,
                   max_results: int = 50) -> List[Dict]:
        """
        List people.

        Args:
            email: Email address filter
            display_name: Display name filter
            max_results: Maximum number of people to return

        Returns:
            List of person objects
        """
        params = {'max': max_results}
        if email:
            params['email'] = email
        if display_name:
            params['displayName'] = display_name

        response = self._request('GET', 'people', params=params)
        return response.get('items', [])

    def get_person(self, person_id: str) -> Dict:
        """
        Get details for a specific person.

        Args:
            person_id: ID of the person

        Returns:
            Person object
        """
        return self._request('GET', f'people/{person_id}')

    def get_person_by_email(self, email: str) -> Optional[Dict]:
        """
        Find a person by email.

        Args:
            email: Email address of the person to find

        Returns:
            Person object or None if not found
        """
        people = self.list_people(email=email)
        if people:
            return people[0]
        return None
