"""
Webex API client for interacting with the Webex API.
"""
import requests
from typing import Dict, List, Optional, Any

from webex_terminal.auth.auth import get_token
from webex_terminal.config import load_config


class WebexAPIError(Exception):
    """Exception raised for Webex API errors.

    This exception is raised when there is an error in the Webex API request,
    such as authentication failures, invalid requests, or server errors.

    Attributes:
        message (str): The error message describing the API error.
    """
    pass


class WebexClient:
    """Client for interacting with the Webex API.

    This class provides methods to interact with various Webex API endpoints,
    including rooms, messages, and people. It handles authentication, request
    formatting, and error handling.

    Attributes:
        config (dict): Configuration settings for the client.
        base_url (str): The base URL for the Webex API.
        session (requests.Session): A session object for making HTTP requests.
    """

    def __init__(self):
        """Initialize the Webex API client.

        This method initializes the client by loading configuration settings,
        setting up the base URL for API requests, and creating a session object
        for making HTTP requests.

        Returns:
            None
        """
        self.config = load_config()
        self.base_url = self.config['api_base_url']
        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        """Get the headers for API requests.

        This method retrieves the authentication token and constructs the
        headers needed for making authenticated requests to the Webex API.

        Returns:
            Dict[str, str]: A dictionary containing the Authorization and Content-Type headers.

        Raises:
            WebexAPIError: If the user is not authenticated.
        """
        token_data = get_token()
        if not token_data:
            raise WebexAPIError("Not authenticated. Please run 'webex-terminal auth' first.")

        return {
            'Authorization': f"Bearer {token_data['access_token']}",
            'Content-Type': 'application/json',
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make a request to the Webex API.

        This method handles the details of making HTTP requests to the Webex API,
        including setting up headers, handling errors, and processing the response.

        Args:
            method (str): The HTTP method to use (GET, POST, PUT, DELETE, etc.).
            endpoint (str): The API endpoint to call, relative to the base URL.
            **kwargs: Additional arguments to pass to the requests library.

        Returns:
            Dict: The JSON response from the API as a dictionary.

        Raises:
            WebexAPIError: If there's an error with the HTTP request or response.
        """
        # Construct the URL manually to preserve case sensitivity
        # The requests library might normalize URLs, which could include transforming to lowercase
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()

        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        # Create a Request object
        req = requests.Request(method, url, headers=headers, **kwargs)

        # Prepare the request
        prepared_req = self.session.prepare_request(req)

        # Send the prepared request
        response = self.session.send(prepared_req)

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
        """Get information about the authenticated user.

        This method retrieves the profile information of the currently
        authenticated user from the Webex API.

        Returns:
            Dict: A dictionary containing the user's profile information.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        return self._request('GET', 'people/me')

    def list_rooms(self, max_results: int = 100) -> List[Dict]:
        """List all rooms the user is a member of.

        This method retrieves a list of all Webex rooms that the authenticated
        user is a member of, up to the specified maximum number of results.

        Args:
            max_results (int, optional): Maximum number of rooms to return. Defaults to 100.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a room.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {'max': max_results}
        response = self._request('GET', 'rooms', params=params)
        return response.get('items', [])

    def get_room(self, room_id: str) -> Dict:
        """Get details for a specific room.

        This method retrieves detailed information about a specific Webex room
        identified by its ID.

        Args:
            room_id (str): ID of the room to retrieve information for.

        Returns:
            Dict: A dictionary containing information about the room.

        Raises:
            WebexAPIError: If there's an error with the API request or if the room doesn't exist.
        """
        # Ensure the room_id is used as-is, without any transformation
        # This is important because Webex room IDs are case-sensitive
        return self._request('GET', f'rooms/{room_id}')

    def get_room_by_name(self, name: str) -> Optional[Dict]:
        """Find a room by name.

        This method searches for a Webex room with the specified name.
        The search is case-insensitive.

        Args:
            name (str): Name of the room to find.

        Returns:
            Optional[Dict]: A dictionary containing information about the room if found,
                           or None if no room with the specified name exists.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        rooms = self.list_rooms()
        for room in rooms:
            if room['title'].lower() == name.lower():
                return room
        return None

    def create_message(self, room_id: str, text: str, markdown: str = None) -> Dict:
        """Send a message to a room.

        This method sends a message to a specified Webex room. The message can be
        sent as plain text or with markdown formatting.

        Args:
            room_id (str): ID of the room to send the message to.
            text (str): Message text in plain text format.
            markdown (str, optional): Message text in markdown format. If provided,
                                     the message will be rendered with markdown formatting.
                                     Defaults to None.

        Returns:
            Dict: A dictionary containing information about the created message.

        Raises:
            WebexAPIError: If there's an error with the API request.
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
        """List messages in a room.

        This method retrieves a list of messages from a specified Webex room,
        up to the specified maximum number of results. Messages are returned
        in reverse chronological order (newest first).

        Args:
            room_id (str): ID of the room to retrieve messages from.
            max_results (int, optional): Maximum number of messages to return. Defaults to 50.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a message.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {
            'roomId': room_id,
            'max': max_results,
        }
        response = self._request('GET', 'messages', params=params)
        return response.get('items', [])

    def get_message(self, message_id: str) -> Dict:
        """Get details for a specific message.

        This method retrieves detailed information about a specific Webex message
        identified by its ID.

        Args:
            message_id (str): ID of the message to retrieve information for.

        Returns:
            Dict: A dictionary containing information about the message.

        Raises:
            WebexAPIError: If there's an error with the API request or if the message doesn't exist.
        """
        return self._request('GET', f'messages/{message_id}')

    def delete_message(self, message_id: str) -> None:
        """Delete a message.

        This method deletes a specific Webex message identified by its ID.
        Only messages created by the authenticated user can be deleted.

        Args:
            message_id (str): ID of the message to delete.

        Returns:
            None

        Raises:
            WebexAPIError: If there's an error with the API request, if the message doesn't exist,
                          or if the user doesn't have permission to delete the message.
        """
        self._request('DELETE', f'messages/{message_id}')

    def list_people(self, email: Optional[str] = None, display_name: Optional[str] = None,
                   max_results: int = 50) -> List[Dict]:
        """List people in the Webex organization.

        This method retrieves a list of people from the Webex organization,
        with optional filtering by email address or display name.

        Args:
            email (Optional[str], optional): Email address filter. Defaults to None.
            display_name (Optional[str], optional): Display name filter. Defaults to None.
            max_results (int, optional): Maximum number of people to return. Defaults to 50.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a person.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {'max': max_results}
        if email:
            params['email'] = email
        if display_name:
            params['displayName'] = display_name

        response = self._request('GET', 'people', params=params)
        return response.get('items', [])

    def get_person(self, person_id: str) -> Dict:
        """Get details for a specific person.

        This method retrieves detailed information about a specific Webex user
        identified by their ID.

        Args:
            person_id (str): ID of the person to retrieve information for.

        Returns:
            Dict: A dictionary containing information about the person.

        Raises:
            WebexAPIError: If there's an error with the API request or if the person doesn't exist.
        """
        return self._request('GET', f'people/{person_id}')

    def get_person_by_email(self, email: str) -> Optional[Dict]:
        """Find a person by email address.

        This method searches for a Webex user with the specified email address.

        Args:
            email (str): Email address of the person to find.

        Returns:
            Optional[Dict]: A dictionary containing information about the person if found,
                           or None if no person with the specified email exists.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        people = self.list_people(email=email)
        if people:
            return people[0]
        return None

    def list_room_members(self, room_id: str, max_results: int = 100) -> List[Dict]:
        """List members of a room.

        This method retrieves a list of all members in a specified Webex room,
        up to the specified maximum number of results.

        Args:
            room_id (str): ID of the room to retrieve members from.
            max_results (int, optional): Maximum number of members to return. Defaults to 100.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a member.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {
            'roomId': room_id,
            'max': max_results,
        }
        response = self._request('GET', 'memberships', params=params)
        return response.get('items', [])

    def create_message_with_file(self, room_id: str, file_path: str, text: str = None) -> Dict:
        """Send a message with a file attachment to a room.

        This method sends a message with a file attachment to a specified Webex room.
        The file is uploaded from the local file system.

        Args:
            room_id (str): ID of the room to send the message to.
            file_path (str): Path to the file to upload.
            text (str, optional): Message text to include with the file. Defaults to None.

        Returns:
            Dict: A dictionary containing information about the created message.

        Raises:
            WebexAPIError: If there's an error with the API request or if the file doesn't exist.
            FileNotFoundError: If the specified file doesn't exist.
        """
        import os

        # Check if file exists
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Prepare the file for upload
        file_name = os.path.basename(file_path)
        files = {
            'files': (file_name, open(file_path, 'rb'), 'application/octet-stream')
        }

        # Prepare the data payload
        data = {
            'roomId': room_id,
        }

        # Add text if provided
        if text:
            data['text'] = text

        # Get headers without Content-Type as it will be set by the multipart request
        headers = self._get_headers()
        headers.pop('Content-Type', None)

        # Make the request
        url = f"{self.base_url}/messages"
        response = self.session.post(url, headers=headers, data=data, files=files)

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
