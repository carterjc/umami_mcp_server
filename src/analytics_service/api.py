import requests
from typing import Optional
import logging

# Configure logging
logger = logging.getLogger("umami-client")

class UmamiClient:
    def __init__(self, base_url: str):
        """
        Initialize the UmamiClient with the base URL of the Umami Analytics API.
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.token = None

    def login(self, username: str, password: str) -> bool:
        """
        Log in to the Umami API using the provided username and password.
        Returns True if login is successful, False otherwise.
        """
        login_url = f"{self.base_url}/api/auth/login"
        payload = {
            "username": username,
            "password": password
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            response = self.session.post(login_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            self.token = data.get("token")
            if self.token:
                # Set the Authorization header for future requests
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                logger.debug("Login successful")
                return True
            else:
                logger.error("Login failed: Token not found in response.")
                return False
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred during login: {http_err} - {response.text}")
            return False
        except Exception as err:
            logger.error(f"An error occurred during login: {err}")
            return False

    def verify_token(self) -> bool:
        """
        Verify the current authentication token.
        Returns True if the token is valid, False otherwise.
        """
        verify_url = f"{self.base_url}/api/auth/verify"
        try:
            response = self.session.post(verify_url)
            response.raise_for_status()
            logger.debug("Token Verified")
            return True
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"Token verification failed: {http_err} - {response.text}")
            return False
        except Exception as err:
            logger.error(f"An error occurred during token verification: {err}")
            return False

    def get_websites(self, team_id: str, query: str = "", page_size: int = 150) -> Optional[dict]:
        """
        Retrieve a list of websites for a given team.
        """
        url = f"{self.base_url}/api/teams/{team_id}/websites"
        params = {
            "query": query,
            "pageSize": page_size
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Retrieved {len(data.get('data', []))} websites.")
            return data
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching websites: {http_err} - {response.text}")
            return None
        except Exception as err:
            logger.error(f"An error occurred while fetching websites: {err}")
            return None

    def get_website_stats(self, website_id: str, start_at: int, end_at: int) -> Optional[dict]:
        """
        Retrieve statistics for a specific website within a time range.
        """
        url = f"{self.base_url}/api/websites/{website_id}/stats"
        params = {
            "startAt": start_at,
            "endAt": end_at
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Retrieved stats for website {website_id}.")
            return data
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching website stats: {http_err} - {response.text}")
            return None
        except Exception as err:
            logger.error(f"An error occurred while fetching website stats: {err}")
            return None
        
    def get_website_metrics(self, website_id: str, start_at: int, end_at: int, type: str) -> Optional[dict]:
        """
        Retrieve metrics for a specific website within a time range.
        """
        url = f"{self.base_url}/api/websites/{website_id}/metrics"
        params = {
            "startAt": start_at,
            "endAt": end_at,
            "type": type
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Retrieved metrics for website {website_id}.")
            return data
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching website metrics: {http_err} - {response.text}")
            return None
        except Exception as err:
            logger.error(f"An error occurred while fetching website metrics: {err}")
            return None

    def get_events_where(self, website_id: str, start_at: int, end_at: int, unit: str, timezone: str, query: str, page: int = 1, page_size: int = 30) -> Optional[dict]:
        """
        Retrieve events based on specific criteria.
        
        Parameters:
            website_id (str): The ID of the website.
            start_at (int): Start timestamp in milliseconds.
            end_at (int): End timestamp in milliseconds.
            unit (str): Time unit (e.g., 'day', 'hour', 'month').
            timezone (str): Timezone (e.g., 'Japan').
            query (str): Query string to filter events (e.g., 'product_details_viewed').
            page (int): Page number for pagination.
            page_size (int): Number of items per page.
        
        Returns:
            dict or None: The JSON response from the API if successful, None otherwise.
        """
        url = f"{self.base_url}/api/websites/{website_id}/events"
        params = {
            "startAt": start_at,
            "endAt": end_at,
            "unit": unit,
            "timezone": timezone,
            "query": query,
            "page": page,
            "pageSize": page_size,
            "search": ""  # Assuming 'search' is optional and empty by default
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Retrieved events with query '{query}' for website {website_id}.")
            return data
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching events: {http_err} - {response.text}")
            return None
        except Exception as err:
            logger.error(f"An error occurred while fetching events: {err}")
            return None

    def get_user_activity(self, website_id: str, session_id: str, start_at: int, end_at: int) -> Optional[dict]:
        """
        Retrieve user activity for a specific session within a time range.
        
        Parameters:
            website_id (str): The ID of the website.
            session_id (str): The ID of the session.
            start_at (int): Start timestamp in milliseconds.
            end_at (int): End timestamp in milliseconds.
        
        Returns:
            dict or None: The JSON response from the API if successful, None otherwise.
        """
        url = f"{self.base_url}/api/websites/{website_id}/sessions/{session_id}/activity"
        params = {
            "startAt": start_at,
            "endAt": end_at
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Retrieved user activity for session {session_id}.")
            return data
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching user activity: {http_err} - {response.text}")
            return None
        except Exception as err:
            logger.error(f"An error occurred while fetching user activity: {err}")
            return None

    def get_pageview_series(self, website_id: str, start_at: int, end_at: int, unit: str, timezone: str) -> Optional[dict]:
        """
        Retrieve pageview data series for a specific website within a time range.
        
        Parameters:
            website_id (str): The ID of the website.
            start_at (int): Start timestamp in milliseconds.
            end_at (int): End timestamp in milliseconds.
            unit (str): Time unit for grouping data (e.g., 'hour', 'day', 'month').
            timezone (str): Timezone for the data (e.g., 'Europe/London', 'UTC').
        
        Returns:
            dict or None: The JSON response containing pageview data if successful, None otherwise.
        """
        url = f"{self.base_url}/api/websites/{website_id}/pageviews"
        params = {
            "startAt": start_at,
            "endAt": end_at,
            "unit": unit,
            "timezone": timezone
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Retrieved pageview series for website {website_id}.")
            return data
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching pageview series: {http_err} - {response.text}")
            return None
        except Exception as err:
            logger.error(f"An error occurred while fetching pageview series: {err}")
            return None

    def get_active(self, website_id: str) -> Optional[dict]:
        """
        Retrieve active visitor data for a specific website.
        
        Parameters:
            website_id (str): The ID of the website to get active visitor data for.
        
        Returns:
            dict or None: The JSON response containing active visitor data if successful, None otherwise.
            The response includes:
            - x: number of active visitors at that timestamp
        """
        url = f"{self.base_url}/api/websites/{website_id}/active"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Retrieved active visitor data for website {website_id}.")
            return data
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching active visitor data: {http_err} - {response.text}")
            return None
        except Exception as err:
            logger.error(f"An error occurred while fetching active visitor data: {err}")
            return None
