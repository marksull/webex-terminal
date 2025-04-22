"""
Webex API client for interacting with the Webex API.
"""
import requests
import re
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
        self.base_url = self.config["api_base_url"]
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
            raise WebexAPIError(
                "Not authenticated. Please run 'webex-terminal auth' first."
            )

        return {
            "Authorization": f"Bearer {token_data['access_token']}",
            "Content-Type": "application/json",
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

        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))


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
                if "message" in error_data:
                    error_msg = f"{error_msg} - {error_data['message']}"
            except:
                pass
            raise WebexAPIError(error_msg)
        except requests.exceptions.RequestException as e:
            raise WebexAPIError(f"Request Error: {e}")
        except ValueError:
            return {}

    def _paginated_get(self, url: str, params: Dict = None, item_key: str = "items", 
                       filter_func=None) -> List[Dict]:
        """Make a paginated GET request to the Webex API.

        This method handles pagination automatically by following the "Link" header
        with rel="next" until all pages have been retrieved. It concatenates the
        results from all pages into a single list.

        Args:
            url (str): The full URL to request.
            params (Dict, optional): Query parameters to include in the request.
            item_key (str, optional): The key in the response JSON that contains the items.
                                     Defaults to "items".
            filter_func (callable, optional): A function to filter the items from each page.
                                             If provided, only items for which this function
                                             returns True will be included in the result.
                                             The function should take a single item as input
                                             and return a boolean.

        Returns:
            List[Dict]: A list of all items from all pages, optionally filtered.

        Raises:
            WebexAPIError: If there's an error with the HTTP request or response.
        """
        headers = self._get_headers()
        all_items = []

        while url:
            # Make the request
            response = self.session.get(url, headers=headers, params=params)

            try:
                response.raise_for_status()
                data = response.json()
                items = data.get(item_key, [])

                # Apply filter if provided
                if filter_func:
                    items = [item for item in items if filter_func(item)]

                all_items.extend(items)

                # Check for Link header for pagination
                link_header = response.headers.get("Link", "")
                url = None

                # Parse Link header to get next page URL
                if link_header:
                    links = link_header.split(",")
                    for link in links:
                        if 'rel="next"' in link:
                            # Extract URL from link
                            url_match = re.search(r"<(.+?)>", link)
                            if url_match:
                                url = url_match.group(1)
                                # Clear params as they're already in the URL
                                params = {}
                                break

            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP Error: {e}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = f"{error_msg} - {error_data['message']}"
                except:
                    pass
                raise WebexAPIError(error_msg)
            except requests.exceptions.RequestException as e:
                raise WebexAPIError(f"Request Error: {e}")
            except ValueError:
                # If we can't parse the JSON, just continue with what we have
                break

        return all_items

    def _head_request(self, endpoint: str, **kwargs) -> Dict:
        """Make a HEAD request to the Webex API and extract information from headers.

        This method handles the details of making HEAD requests to the Webex API,
        including setting up headers, handling errors, and extracting information
        from the response headers.

        Args:
            endpoint (str): The API endpoint to call, relative to the base URL.
            **kwargs: Additional arguments to pass to the requests library.

        Returns:
            Dict: A dictionary containing information extracted from the response headers.

        Raises:
            WebexAPIError: If there's an error with the HTTP request or response.
        """
        # Construct the URL manually to preserve case sensitivity
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()

        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        try:
            # Make the HEAD request
            response = self.session.head(url, headers=headers, **kwargs)
            response.raise_for_status()

            # Extract information from headers
            result = {}

            # Get filename from Content-Disposition header
            content_disposition = response.headers.get("Content-Disposition", "")
            if "filename=" in content_disposition:
                # Extract filename from Content-Disposition header
                # Format is typically: attachment; filename="example.pdf"
                filename_match = re.search(
                    r'filename=["\']?([^"\';\n]+)["\']?', content_disposition
                )
                if filename_match:
                    result["name"] = filename_match.group(1)

            # Get content type
            content_type = response.headers.get("Content-Type", "")
            if content_type:
                result["contentType"] = content_type

            # Get content length (file size)
            content_length = response.headers.get("Content-Length", "")
            if content_length and content_length.isdigit():
                result["size"] = int(content_length)

            # Add all other headers that might be useful
            for header, value in response.headers.items():
                # Convert header names to camelCase to match Webex API convention
                header_parts = header.split("-")
                camel_case_header = header_parts[0].lower() + "".join(
                    part.capitalize() for part in header_parts[1:]
                )

                # Add header to result if not already added
                if camel_case_header not in result:
                    result[camel_case_header] = value

            return result

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error: {e}"
            raise WebexAPIError(error_msg)
        except requests.exceptions.RequestException as e:
            raise WebexAPIError(f"Request Error: {e}")
        except Exception as e:
            raise WebexAPIError(f"Unexpected error: {e}")

    def get_me(self) -> Dict:
        """Get information about the authenticated user.

        This method retrieves the profile information of the currently
        authenticated user from the Webex API.

        Returns:
            Dict: A dictionary containing the user's profile information.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        return self._request("GET", "people/me")

    def list_rooms(self, max_results: int = 100, title_contains: str = None) -> List[Dict]:
        """List all rooms the user is a member of.

        This method retrieves a list of all Webex rooms that the authenticated
        user is a member of. It handles pagination automatically to retrieve all rooms,
        and can optionally filter rooms by title.

        Args:
            max_results (int, optional): Maximum number of rooms to return per page. Defaults to 100.
            title_contains (str, optional): If provided, only rooms with titles containing this string
                                           will be returned. The filtering is done on the server side.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a room.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {"max": max_results}

        # Add title filter if provided
        if title_contains:
            params["title"] = title_contains

        # Use the paginated_get helper method
        url = f"{self.base_url}/rooms"
        return self._paginated_get(url, params)

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
        return self._request("GET", f"rooms/{room_id}")

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
        # Use the title_contains parameter for server-side filtering to narrow down the results
        rooms = self.list_rooms(title_contains=name)

        # Then find the exact match (case-insensitive)
        for room in rooms:
            if room["title"].lower() == name.lower():
                return room
        return None

    def search_rooms_by_name(self, name: str) -> List[Dict]:
        """Search for rooms by partial name.

        This method searches for Webex rooms whose names contain the specified string.
        The search is case-insensitive and performed on the server side.

        Args:
            name (str): Partial name to search for.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a matching room.
                       Returns an empty list if no rooms match the search.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        # Use the title_contains parameter for server-side filtering
        return self.list_rooms(title_contains=name)

    def create_message(self, room_id: str, text: str, markdown: str = None, parent_id: str = None) -> Dict:
        """Send a message to a room.

        This method sends a message to a specified Webex room. The message can be
        sent as plain text or with markdown formatting.

        Args:
            room_id (str): ID of the room to send the message to.
            text (str): Message text in plain text format.
            markdown (str, optional): Message text in markdown format. If provided,
                                     the message will be rendered with markdown formatting.
                                     Defaults to None.
            parent_id (str, optional): ID of the parent message to thread this message under.
                                      If provided, this message will be part of a thread.
                                      Defaults to None.

        Returns:
            Dict: A dictionary containing information about the created message.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        data = {
            "roomId": room_id,
            "text": text,
        }

        # Include markdown in the payload if provided
        if markdown:
            data["markdown"] = markdown

        # Include parentId in the payload if provided
        if parent_id:
            data["parentId"] = parent_id

        return self._request("POST", "messages", json=data)

    def list_messages(self, room_id: str, max_results: int = 50) -> List[Dict]:
        """List messages in a room.

        This method retrieves a list of messages from a specified Webex room.
        It handles pagination automatically to retrieve all messages.
        Messages are returned in reverse chronological order (newest first).

        Args:
            room_id (str): ID of the room to retrieve messages from.
            max_results (int, optional): Maximum number of messages to return per page. Defaults to 50.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a message.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {
            "roomId": room_id,
            "max": max_results,
        }

        # Use the paginated_get helper method
        url = f"{self.base_url}/messages"
        return self._paginated_get(url, params)

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
        return self._request("GET", f"messages/{message_id}")

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
        self._request("DELETE", f"messages/{message_id}")

    def list_people(
        self,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        max_results: int = 50,
    ) -> List[Dict]:
        """List people in the Webex organization.

        This method retrieves a list of people from the Webex organization,
        with optional filtering by email address or display name.
        It handles pagination automatically to retrieve all matching people.

        Args:
            email (Optional[str], optional): Email address filter. Defaults to None.
            display_name (Optional[str], optional): Display name filter. Defaults to None.
            max_results (int, optional): Maximum number of people to return per page. Defaults to 50.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a person.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {"max": max_results}
        if email:
            params["email"] = email
        if display_name:
            params["displayName"] = display_name

        # Use the paginated_get helper method
        url = f"{self.base_url}/people"
        return self._paginated_get(url, params)

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
        return self._request("GET", f"people/{person_id}")

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

        This method retrieves a list of all members in a specified Webex room.
        It handles pagination automatically to retrieve all members.

        Args:
            room_id (str): ID of the room to retrieve members from.
            max_results (int, optional): Maximum number of members to return per page. Defaults to 100.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a member.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {
            "roomId": room_id,
            "max": max_results,
        }

        # Use the paginated_get helper method
        url = f"{self.base_url}/memberships"
        return self._paginated_get(url, params)

    def add_user_to_room(self, room_id: str, email: str) -> Dict:
        """Add a user to a room.

        This method adds a user to a specified Webex room using their email address.

        Args:
            room_id (str): ID of the room to add the user to.
            email (str): Email address of the user to add.

        Returns:
            Dict: A dictionary containing information about the created membership.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        data = {
            "roomId": room_id,
            "personEmail": email,
        }
        response = self._request("POST", "memberships", json=data)
        return response

    def create_message_with_file(
        self, room_id: str, file_path: str, text: str = None
    ) -> Dict:
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
            "files": (file_name, open(file_path, "rb"), "application/octet-stream")
        }

        # Prepare the data payload
        data = {
            "roomId": room_id,
        }

        # Add text if provided
        if text:
            data["text"] = text

        # Get headers without Content-Type as it will be set by the multipart request
        headers = self._get_headers()
        headers.pop("Content-Type", None)

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
                if "message" in error_data:
                    error_msg = f"{error_msg} - {error_data['message']}"
            except:
                pass
            raise WebexAPIError(error_msg)
        except requests.exceptions.RequestException as e:
            raise WebexAPIError(f"Request Error: {e}")
        except ValueError:
            return {}

    def list_files(self, room_id: str, max_results: int = 100) -> List[Dict]:
        """List files available in a room.

        This method retrieves a list of all files that have been shared in a room.
        It handles pagination automatically to retrieve all messages with file attachments.

        Args:
            room_id (str): ID of the room to search for files.
            max_results (int, optional): Maximum number of messages to retrieve per page. Defaults to 100.
                                        This parameter is passed to the list_messages method.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a file.
                        Each dictionary contains 'filename', 'url', 'message_id', 'id', and other
                        file details like 'contentType', 'size', 'created', 'creatorId', etc.
                        The 'filename' is the human-readable filename, while 'id' is the file ID.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        # Get all messages in the room (list_messages now handles pagination)
        messages = self.list_messages(room_id, max_results=max_results)

        # List to store file information
        files = []

        # Search for messages with file attachments
        for message in messages:
            # Check if the message has files
            if "files" in message:
                # Get the message details to get file information
                message_details = self.get_message(message["id"])

                # Check if the message has files
                if "files" in message_details:
                    for file_url in message_details["files"]:
                        if isinstance(file_url, str):
                            # Extract file ID from URL (the last part of the URL)
                            file_id = file_url.split("/")[-1]

                            # Get file details from the API
                            try:
                                file_details = self.get_file_details(file_id)

                                # Check if file_details is empty
                                if file_details:
                                    # Create a file info dictionary with all the details
                                    file_info = {
                                        "filename": file_details.get("name", file_id),
                                        "url": file_url,
                                        "message_id": message["id"],
                                        "id": file_id,
                                        "contentType": file_details.get("contentType"),
                                        "size": file_details.get("size"),
                                        "created": file_details.get("created"),
                                        "creatorId": file_details.get("creatorId"),
                                        "downloadUrl": file_details.get("downloadUrl"),
                                    }

                                    # Add any other fields from file_details to file_info
                                    for key, value in file_details.items():
                                        if key not in file_info:
                                            file_info[key] = value

                                    # Add file info to the list
                                    files.append(file_info)
                                else:
                                    # If file_details is empty, fall back to the old method
                                    # but don't raise an exception
                                    raise WebexAPIError("Empty file details")
                            except WebexAPIError:
                                # If we can't get file details, fall back to the old method
                                import re

                                # Look for actual filename in message details
                                # Check common fields that might contain the filename
                                actual_filename = None

                                # Check if there's a 'fileName' field in the message
                                if "fileName" in message_details:
                                    actual_filename = message_details["fileName"]
                                # Check if there's a 'content' field with filename info
                                elif "content" in message_details and isinstance(
                                    message_details["content"], dict
                                ):
                                    if "fileName" in message_details["content"]:
                                        actual_filename = message_details["content"][
                                            "fileName"
                                        ]
                                    elif "name" in message_details["content"]:
                                        actual_filename = message_details["content"][
                                            "name"
                                        ]
                                    # Check for files array in content
                                    elif "files" in message_details[
                                        "content"
                                    ] and isinstance(
                                        message_details["content"]["files"], list
                                    ):
                                        for file_item in message_details["content"][
                                            "files"
                                        ]:
                                            if isinstance(file_item, dict):
                                                if "name" in file_item:
                                                    actual_filename = file_item["name"]
                                                    break
                                                elif "fileName" in file_item:
                                                    actual_filename = file_item[
                                                        "fileName"
                                                    ]
                                                    break
                                                elif "displayName" in file_item:
                                                    actual_filename = file_item[
                                                        "displayName"
                                                    ]
                                                    break
                                # Check if there's an 'attachments' field
                                elif "attachments" in message_details and isinstance(
                                    message_details["attachments"], list
                                ):
                                    for attachment in message_details["attachments"]:
                                        if isinstance(attachment, dict):
                                            if "fileName" in attachment:
                                                actual_filename = attachment["fileName"]
                                                break
                                            elif "name" in attachment:
                                                actual_filename = attachment["name"]
                                                break
                                            elif "contentName" in attachment:
                                                actual_filename = attachment[
                                                    "contentName"
                                                ]
                                                break
                                            elif "displayName" in attachment:
                                                actual_filename = attachment[
                                                    "displayName"
                                                ]
                                                break
                                            # Check for content field in attachment
                                            elif "content" in attachment and isinstance(
                                                attachment["content"], dict
                                            ):
                                                if "fileName" in attachment["content"]:
                                                    actual_filename = attachment[
                                                        "content"
                                                    ]["fileName"]
                                                    break
                                                elif "name" in attachment["content"]:
                                                    actual_filename = attachment[
                                                        "content"
                                                    ]["name"]
                                                    break

                                # Try to extract filename from the URL path
                                if not actual_filename:
                                    # The URL might contain the filename in the path
                                    url_filename_match = re.search(
                                        r"/([^/]+\.[a-zA-Z0-9]+)(?:\?|$)",
                                        file_url,
                                        re.IGNORECASE,
                                    )
                                    if url_filename_match:
                                        actual_filename = url_filename_match.group(1)

                                # If we couldn't find the actual filename, try to extract it from the text
                                if not actual_filename and "text" in message_details:
                                    # Look for patterns like "filename: something.txt" or "uploaded: something.txt"
                                    text = message_details["text"]
                                    # Try different patterns
                                    filename_patterns = [
                                        r"(?:filename|file|uploaded|attached):\s*([^\s]+\.[a-zA-Z0-9]+)",
                                        r"uploaded\s+([^\s]+\.[a-zA-Z0-9]+)",
                                        r"attached\s+([^\s]+\.[a-zA-Z0-9]+)",
                                        r"file\s+([^\s]+\.[a-zA-Z0-9]+)",
                                        r"([^\s]+\.[a-zA-Z0-9]{2,4})",  # Look for any word ending with a file extension
                                    ]

                                    for pattern in filename_patterns:
                                        filename_match = re.search(
                                            pattern, text, re.IGNORECASE
                                        )
                                        if filename_match:
                                            actual_filename = filename_match.group(1)
                                            break

                                # If we still couldn't find the actual filename, use the file ID
                                if not actual_filename:
                                    actual_filename = file_id

                                # Add file info to the list with limited information
                                files.append(
                                    {
                                        "filename": actual_filename,
                                        "url": file_url,
                                        "message_id": message["id"],
                                        "id": file_id,
                                    }
                                )

        return files

    def get_file_details(self, file_id: str) -> Dict:
        """Get details for a specific file.

        This method retrieves detailed information about a specific file
        identified by its ID.

        Args:
            file_id (str): ID of the file to retrieve information for.

        Returns:
            Dict: A dictionary containing information about the file, including:
                name: The actual filename.
                contentType: The MIME type of the file.
                size: The size of the file in bytes.
                created: The timestamp when the file was created.
                creatorId: The ID of the user who uploaded the file.
                downloadUrl: A URL that can be used to download the file content.
                And other relevant details.

        Raises:
            WebexAPIError: If there's an error with the API request or if the file doesn't exist.
        """
        # Use a HEAD request to get file details from headers
        # According to Webex API documentation, this is the recommended way to get file details
        try:
            # Make a HEAD request to the contents endpoint
            file_details = self._head_request(f"contents/{file_id}")

            # If we got file details, add the download URL
            if file_details:
                file_details["downloadUrl"] = f"{self.base_url}/contents/{file_id}"

            return file_details
        except WebexAPIError as e:
            # If HEAD request fails, try the traditional GET requests as fallback
            try:
                result = self._request("GET", f"contents/{file_id}")
                return result
            except WebexAPIError as e:
                # If that fails, try the attachment/actions endpoint
                try:
                    result = self._request("GET", f"attachment/actions/{file_id}")
                    return result
                except WebexAPIError as e:
                    # If that also fails, try the attachment endpoint
                    try:
                        result = self._request("GET", f"attachment/{file_id}")
                        return result
                    except WebexAPIError as e:
                        # If all endpoints fail, return an empty dictionary
                        return {}

    def download_file_from_url(self, file_url: str, save_path: str = None) -> str:
        """Download a file directly from a URL.

        This method downloads a file from a given URL and saves it to the local file system.
        It displays a progress bar during the download.

        Args:
            file_url (str): URL of the file to download.
            save_path (str, optional): Path where the file should be saved.
                                      If not provided, the file will be saved
                                      in a temporary directory.

        Returns:
            str: The path where the file was saved.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        import os
        import tempfile
        from tqdm import tqdm

        # Get headers for authentication
        headers = self._get_headers()

        # Determine save path
        if not save_path:
            # Create a temporary directory if it doesn't exist
            temp_dir = os.path.join(tempfile.gettempdir(), "webex-terminal")
            os.makedirs(temp_dir, exist_ok=True)

            # Generate a unique filename based on the URL
            import hashlib
            filename = hashlib.md5(file_url.encode()).hexdigest()

            # Try to determine file extension from URL
            if "." in file_url.split("/")[-1]:
                ext = file_url.split("/")[-1].split(".")[-1]
                filename = f"{filename}.{ext}"

            save_path = os.path.join(temp_dir, filename)

        # Download the file
        response = self.session.get(file_url, headers=headers, stream=True)
        response.raise_for_status()

        # Get file size from headers if available
        total_size = int(response.headers.get('content-length', 0))

        # Create a progress bar
        desc = f"Downloading {os.path.basename(save_path)}"

        # Save the file with progress bar
        with open(save_path, "wb") as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=desc) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        pbar.update(len(chunk))

        return save_path

    def list_teams(self, max_results: int = 100) -> List[Dict]:
        """List all teams the user is a member of.

        This method retrieves a list of all Webex teams that the authenticated
        user is a member of. It handles pagination automatically to retrieve all teams.

        Args:
            max_results (int, optional): Maximum number of teams to return per page. Defaults to 100.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a team.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        params = {"max": max_results}

        # Use the paginated_get helper method
        url = f"{self.base_url}/teams"
        return self._paginated_get(url, params)

    def list_team_rooms(self, team_id: str, max_results: int = 100) -> List[Dict]:
        """List all rooms (spaces) in a specific team.

        This method retrieves a list of all Webex rooms that are associated with
        the specified team. It handles pagination automatically to retrieve all rooms.

        Args:
            team_id (str): ID of the team to retrieve rooms for.
            max_results (int, optional): Maximum number of rooms to return per page. Defaults to 100.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a room.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        # Use the Webex API to get rooms filtered by teamId
        params = {
            "teamId": team_id,
            "max": max_results
        }

        # Define a filter function to ensure we only return rooms that are actually part of the team
        def filter_team_rooms(room):
            return room.get('teamId') == team_id

        # Use the paginated_get helper method with the filter function
        url = f"{self.base_url}/rooms"
        return self._paginated_get(url, params, filter_func=filter_team_rooms)

    def remove_user_from_room(self, room_id: str, email: str) -> Dict:
        """Remove a user from a room.

        This method removes a user from a specified Webex room using their email address.
        It first finds the membership ID for the user in the room, then deletes that membership.

        Args:
            room_id (str): ID of the room to remove the user from.
            email (str): Email address of the user to remove.

        Returns:
            Dict: A dictionary containing information about the deleted membership.

        Raises:
            WebexAPIError: If there's an error with the API request or if the user is not found in the room.
        """
        # Get all memberships for the room
        memberships = self.list_room_members(room_id)

        # Find the membership for the specified email
        membership_id = None
        for membership in memberships:
            if membership.get("personEmail", "").lower() == email.lower():
                membership_id = membership.get("id")
                break

        if not membership_id:
            raise WebexAPIError(f"User with email '{email}' not found in the room.")

        # Delete the membership
        response = self._request("DELETE", f"memberships/{membership_id}")
        return response

    def list_room_tabs(self, room_id: str) -> List[Dict]:
        """List all tabs (URLs) associated with a room.

        This method retrieves a list of all tabs (URLs) that are associated with
        the specified room.

        Args:
            room_id (str): ID of the room to retrieve tabs for.

        Returns:
            List[Dict]: A list of dictionaries, each containing information about a tab.

        Raises:
            WebexAPIError: If there's an error with the API request.
        """
        # Make the API request to the room/tabs endpoint
        response = self._request("GET", f"room/tabs?roomId={room_id}")
        return response.get("items", [])

    def download_file(self, room_id: str, filename: str, save_path: str = None) -> str:
        """Download a file from a room.

        This method searches for a file with the specified filename or ID in a room
        and downloads it to the local file system. It displays a progress bar during
        the download.

        Args:
            room_id (str): ID of the room to search for the file.
            filename (str): Name or ID of the file to download.
            save_path (str, optional): Path where the file should be saved.
                                      If not provided, the file will be saved
                                      in the current directory.

        Returns:
            str: The path where the file was saved.

        Raises:
            WebexAPIError: If there's an error with the API request.
            FileNotFoundError: If the specified file is not found in the room.
        """
        import os
        from tqdm import tqdm

        # Get list of files in the room
        files = self.list_files(room_id)

        # Search for the file by name or ID
        file_url = None
        download_url = None
        actual_filename = None
        for file_info in files:
            # Check if the filename matches exactly (case-insensitive)
            if file_info["filename"].lower() == filename.lower():
                file_url = file_info["url"]
                download_url = file_info.get("downloadUrl")
                actual_filename = file_info["filename"]
                break
            # Check if the filename is contained in the file URL
            elif filename.lower() in file_info["url"].lower():
                file_url = file_info["url"]
                download_url = file_info.get("downloadUrl")
                actual_filename = file_info["filename"]
                break
            # Check if the filename matches the file ID
            elif "id" in file_info and file_info["id"].lower() == filename.lower():
                file_url = file_info["url"]
                download_url = file_info.get("downloadUrl")
                actual_filename = file_info["filename"]
                break
            # Check if the filename is a substring of the actual filename (case-insensitive)
            elif filename.lower() in file_info["filename"].lower():
                file_url = file_info["url"]
                download_url = file_info.get("downloadUrl")
                actual_filename = file_info["filename"]
                break

        # If file not found, raise an error
        if not file_url and not download_url:
            raise FileNotFoundError(f"File not found in room: {filename}")

        # Use the actual filename for saving the file
        if not actual_filename:
            actual_filename = filename

        # Clean up the filename to make it safe for the filesystem
        # Remove any characters that might cause issues in filenames
        import re

        safe_filename = re.sub(r'[\\/*?:"<>|]', "_", actual_filename)

        # Determine save path
        if not save_path:
            save_path = os.path.join(os.getcwd(), safe_filename)
        else:
            # If save_path is a directory, append the filename
            if os.path.isdir(save_path):
                save_path = os.path.join(save_path, safe_filename)

        # Get headers for authentication
        headers = self._get_headers()

        # Use download_url if available, otherwise use file_url
        url_to_use = download_url if download_url else file_url

        # Download the file
        response = self.session.get(url_to_use, headers=headers, stream=True)
        response.raise_for_status()

        # Get file size from headers if available
        total_size = int(response.headers.get('content-length', 0))

        # Create a progress bar
        desc = f"Downloading {safe_filename}"

        # Save the file with progress bar
        with open(save_path, "wb") as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=desc) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        pbar.update(len(chunk))

        return save_path
