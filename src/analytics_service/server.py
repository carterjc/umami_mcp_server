import os
import json
from typing import Any, Sequence
import sys
from datetime import datetime

from dotenv import load_dotenv
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from .api import UmamiClient
from .embeddings import get_chunks
from .crawler import CrawlingAPI

def convert_date_to_unix(date_str: str, end_of_day: bool = False) -> int:
    """
    Convert a date string to Unix timestamp in milliseconds.
    Format should be YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
    
    Args:
        date_str (str): Date string in format YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
        end_of_day (bool): If True and time not provided, set time to 23:59:59.999
        
    Returns:
        int: Unix timestamp in milliseconds
    """
    try:
        # Try parsing with time first
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            # If that fails, try just date
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            # If end_of_day is True, set time to end of day
            if end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=999000)
            
        # Convert to milliseconds
        return int(dt.timestamp() * 1000)
    except ValueError as e:
        raise ValueError(f"Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS. Error: {str(e)}")

# Load environment variables
load_dotenv()

# API configuration
API_BASE_URL = os.getenv("UMAMI_API_URL")
API_USERNAME = os.getenv("UMAMI_USERNAME")
API_PASSWORD = os.getenv("UMAMI_PASSWORD")
TEAM_ID = os.getenv("UMAMI_TEAM_ID")

if not all([API_BASE_URL, API_USERNAME, API_PASSWORD, TEAM_ID]):
    raise ValueError("Missing required environment variables")

# Initialize API client
client = UmamiClient(API_BASE_URL)
crawler = CrawlingAPI()

# Ensure client is logged in at startup
if not client.login(API_USERNAME, API_PASSWORD):
    raise RuntimeError("Failed to login to Umami API")
if not client.verify_token():
    raise RuntimeError("Failed to verify Umami API token")

# Create server instance
app = Server("analytics-server")

def get_session_ids(website_id, event_name, start_at, end_at):
    """
    Retrieve session IDs for a specific event on a website.
    
    Args:
    website_id (str): ID of the website
    event_name (str): Name of the event to filter by
    
    Returns:
    list: Unique session IDs associated with the event
    """
    ids = []
    page = 1
    while True:
        events_where = client.get_events_where(
            website_id=website_id,
            start_at=start_at,
            end_at=end_at,
            unit="day",
            timezone="UTC",
            query=event_name,
            page=page,
            page_size=200
        )
        if events_where:
            db = (list({event['sessionId'] for event in events_where['data']}))
            for i in db:
                ids.append(i)
        if 200 * events_where['page'] >= events_where['count']:
            break
        else:
            page += 1
    return list(set(ids))

# List of tools and their descriptions for LLM
@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tracking data tools."""
    return [
        Tool(
            name="get_websites",
            description="""Retrieve a list of the websites present in the tracking database.
            This tool does not require any input.
            The output of this tool includes the following fields for each website:
            - id: The unique identifier of the website
            - name: The name of the website
            - domain: The URL of the website
            - shareId: The unique identifier that can connect websites together
            - resetAt: The date and time when the website was last reset
            - userId: The unique identifier of the user that owns the website
            - teamId: The unique identifier of the team that owns the website
            - createdBy: The unique identifier of the user that created the website
            - createdAt: The date and time when the website was created
            - updatedAt: The date and time when the website was last updated
            - deletedAt: The date and time when the website was deleted
            - createUser: The unique identifier of the user that created the website, and their username
            """,
            inputSchema={
                "type": "object",
                "properties": {
                }
            }
        ),
        Tool(
            name="get_tracking_data",
            description="Get the user journey for a specific session ID within a time range. Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {
                        "type": "string",
                        "description": "The ID of the website where the user journey is located"
                    },
                    "start_at": {
                        "type": "string",
                        "description": """Start date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 00:00:00
                            - 2024-01-31
                            Note: If time is not provided, 00:00:00 will be used"""
                    },
                    "end_at": {
                        "type": "string",
                        "description": """End date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 23:59:59
                            - 2024-01-31
                            Note: If time is not provided, 23:59:59.999 will be used"""
                    },
                    "session_id": {
                        "type": "string",
                        "description": "ID of the user session to get tracking data for"
                    }
                },
                "required": ["website_id", "start_at", "end_at", "session_id"]
            }
        ),
        Tool(
            name="get_website_stats",
            description="""Get the 5 overivew metrics for a specific website within a time range. The returned metrics are as follows:
            - pageviews: The number of total pageviews for the entire website
            - visitors: The number of unique visitors the website has had
            - visits: The number of unique visits those visitors have had to the website
            - bounces: The number of visitors that left the website without interacting with it
            - totaltime: The total time spent on the website by all visitors
            
            Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {
                        "type": "string",
                        "description": "ID of the website to get overivew stats for"
                    },
                    "start_at": {
                        "type": "string",
                        "description": """Start date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 00:00:00
                            - 2024-01-31
                            Note: If time is not provided, 00:00:00 will be used"""
                    },
                    "end_at": {
                        "type": "string",
                        "description": """End date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 23:59:59
                            - 2024-01-31
                            Note: If time is not provided, 23:59:59.999 will be used"""
                    }
                },
                "required": ["website_id", "start_at", "end_at"]
            }
        ),
        Tool(
            name="get_session_ids",
            description="""Get a list of the unique session IDs who visited a specific website within a time range and perform a specific event.
            WARNING: due to api limitations, only the first 1000 total session IDs will be returned by the api. Within those less will be unique.
            Do not use this tool to calculate the number of unique visitors - only use it to get session IDs.
            
            Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {
                        "type": "string",
                        "description": "ID of the website to get session IDs for"
                    },
                    "start_at": {
                        "type": "string",
                        "description": """Start date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 00:00:00
                            - 2024-01-31
                            Note: If time is not provided, 00:00:00 will be used"""
                    },
                    "end_at": {
                        "type": "string",
                        "description": """End date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 23:59:59
                            - 2024-01-31
                            Note: If time is not provided, 23:59:59.999 will be used"""
                    },
                    "event_name": {
                        "type": "string",
                        "description": """Name of the event to filter by. Here are the possible events:
                        - product_details_viewed
                        - product_clicked
                        - user_sign_in
                        - product_added_to_cart
                        - checkout_started
                        - language_changed
                        - checkout_completed
                        If not filtering by an event, set this to None.
                        """
                    }
                },
                "required": ["website_id", "start_at", "end_at", "event_name"]
            }
        ),
        Tool(
            name="get_website_metrics",
            description="""Get various metrics for a specific website within a time range and how many visitors have had each metric.
            The metric type is selected by type property.
            
            Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {
                        "type": "string",
                        "description": "ID of the website to get metrics for"
                    },
                    "start_at": {
                        "type": "string",
                        "description": """Start date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 00:00:00
                            - 2024-01-31
                            Note: If time is not provided, 00:00:00 will be used"""
                    },
                    "end_at": {
                        "type": "string",
                        "description": """End date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 23:59:59
                            - 2024-01-31
                            Note: If time is not provided, 23:59:59.999 will be used"""
                    },
                    "type": {
                        "type": "string",
                        "description": """Type of metrics to retrieve. Here are the possible types:
                        - url: The number of visits for each URL on the website (effectively the number times each page has been visited)
                        - referrer: Where the visitors came from to get to the website
                        - browser: Which browser the visitors used to visit the website
                        - os: Which operating system the visitors used to visit the website
                        - device: Which device the visitors used to visit the website
                        - country: Which country the visitors are from
                        - event: The tally of each event that has occurred on the website
                        """
                    }
                },
                "required": ["website_id", "start_at", "end_at", "type"]
            }
        ),
        Tool(
            name="get_docs",
            description="""Performs the document selection and retrieval part of the RAG pipeline for user journeys from umami tracking data.
            User journey data is retrieved for all users who performed the selected event. Then the data is then chunked into documents and embedded into a vector database.
            Similarity search based of the users question is then used to retrieve the most relevant documents. These documents are returned for use in answering the user's question.
            
            Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_question": {
                        "type": "string",
                        "description": """The user's question to be used to retrieve relevant documents. 
                        This does not have to be word for word the same as the question the user asked, but should allow for the most relevant documents to be retrieved."""
                    },
                    "selected_event": {
                        "type": "string",
                        "description": """The event to filter the session ids by. Here are the possible events:
                        - product_details_viewed
                        - product_clicked
                        - user_sign_in
                        - product_added_to_cart
                        - checkout_started
                        - language_changed
                        - checkout_completed
                        If not filtering by an event, set this to None."""
                    },
                    "website_id": { 
                        "type": "string",
                        "description": "The ID of the website to get user journey data from"
                    },
                    "start_at": {
                        "type": "string",
                        "description": """Start date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 00:00:00
                            - 2024-01-31
                            Note: If time is not provided, 00:00:00 will be used"""
                    },
                    "end_at": {
                        "type": "string",
                        "description": """End date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 23:59:59
                            - 2024-01-31
                            Note: If time is not provided, 23:59:59.999 will be used"""
                    }
                },
                "required": ["user_question", "selected_event", "website_id", "start_at", "end_at"]
            }
        ),
        Tool(
            name="get_screenshot",
            description="Get a screenshot of a webpage for a specified URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the webpage to screenshot for"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="get_html",
            description="Get the HTML code of a webpage for a specified URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the webpage to get the HTML code for"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="get_pageview_series",
            description="""Get the pageview data series for a specific website within a time range. 
            The data is grouped by the specified time unit (hour, day, month) and includes the number 
            of pageviews and sessions for each time period.
            
            Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {
                        "type": "string",
                        "description": "ID of the website to get pageview data for"
                    },
                    "start_at": {
                        "type": "string",
                        "description": """Start date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 00:00:00
                            - 2024-01-31
                            Note: If time is not provided, 00:00:00 will be used"""
                    },
                    "end_at": {
                        "type": "string",
                        "description": """End date for time range of data to retrieve.
                            Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
                            Examples:
                            - 2024-03-01
                            - 2024-03-01 23:59:59
                            - 2024-01-31
                            Note: If time is not provided, 23:59:59.999 will be used"""
                    },
                    "unit": {
                        "type": "string",
                        "description": "Time unit for grouping data (hour, day, or month)",
                        "enum": ["hour", "day", "month"]
                    },
                    "timezone": {
                        "type": "string",
                        "description": "Timezone for the data (e.g., 'UTC', 'Europe/London')"
                    }
                },
                "required": ["website_id", "start_at", "end_at", "unit", "timezone"]
            }
        ),
        Tool(
            name="get_active_visitors",
            description="""Get the current number of active visitors on a specific website. 
            This provides real-time data about how many visitors are currently on the website.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {
                        "type": "string",
                        "description": "ID of the website to get active visitor data for"
                    }
                },
                "required": ["website_id"]
            }
        )
    ]

@app.list_prompts()
async def list_prompts():
    """List available prompts for analytics dashboard creation."""
    return [
        {
            "name": "Create Dashboard",
            "description": "Guide for creating comprehensive analytics dashboards using website metrics and stats",
            "arguments": [
                {
                    "name": "Website Name",
                    "description": "Name of the website to analyze",
                    "required": True
                },
                {
                    "name": "Start Date (YYYY-MM-DD)",
                    "description": "Start date for analysis (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
                    "required": True
                },
                {
                    "name": "End Date (YYYY-MM-DD)", 
                    "description": "End date for analysis (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
                    "required": True
                },
                {
                    "name": "Timezone",
                    "description": "Timezone for the analysis (e.g., 'UTC', 'Europe/London')",
                    "required": True
                }
            ]
        }
    ]

@app.get_prompt()
async def get_prompt(name: str, arguments: Any):
    """Handle prompt requests."""
    if name == "Create Dashboard":
        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"""You are an analytics expert helping to create a comprehensive dashboard using website tracking data. 
Follow these steps to create an attractive and engaging dashboard for website: {arguments['Website Name']}, analyzing data from {arguments['Start Date (YYYY-MM-DD)']} to {arguments['End Date (YYYY-MM-DD)']} in timezone {arguments['Timezone']}.
To begin, get the website id using get_websites and find the id of the website with the name {arguments['Website Name']}. Then use the id to get the other data.

1. OVERVIEW METRICS
First, get the high-level website statistics using get_website_stats:
- Total pageviews
- Unique visitors
- Total visits
- Bounce rate
- Total time spent

2. TIME-BASED ANALYSIS
Use get_pageview_series to analyze traffic patterns:
- Get hourly data for short time ranges (1-7 days)
- Get daily data for medium ranges (8-90 days)
- Get monthly data for long ranges (90+ days)
- Look for patterns in peak usage times
- Identify trends in visitor engagement

3. USER BEHAVIOR METRICS
Use get_website_metrics to analyze:

a) Page Performance (type: "url")
- Most visited pages
- Entry and exit pages
- Time spent per page

b) Traffic Sources (type: "referrer")
- Top referral sources
- Direct vs indirect traffic
- Search engine performance

c) User Technology (types: "browser", "os", "device")
- Browser usage
- Operating system distribution
- Device type preferences

d) Geographic Data (type: "country")
- User distribution by country
- Regional engagement patterns

e) Event Analysis (type: "event")
- Key user interactions
- Conversion events
- User journey milestones

4. ACTIVE USERS
Use get_active_visitors to:
- Monitor current site activity
- Compare with historical averages
- Track real-time engagement

5. USER JOURNEY ANALYSIS
For deeper insights into specific behaviors:
a) Use get_session_ids to identify relevant user sessions
b) Use get_tracking_data to analyze specific user journeys
c) Use get_docs to find patterns in user behavior

6. VISUAL CONTEXT
When needed:
- Use get_screenshot to capture page layouts
- Use get_html to analyze page structure

PRESENTATION GUIDELINES:
1. Start with the most important metrics for your audience
2. Group related metrics together
3. Show trends over time where possible
4. Highlight significant changes or patterns
5. Include context and explanations for metrics
6. Consider different time ranges for different metrics
7. Focus on actionable insights

Remember to:
- Validate all date ranges before analysis
- Consider timezone effects on data
- Look for correlations between different metrics
- Highlight unusual patterns or anomalies
- Provide context for significant changes
- Consider seasonal or temporal factors
- Focus on metrics that drive business decisions

Start by gathering the overview metrics and then proceed through each analysis section systematically. Only create once you are satisfied you have gathered all the data you need.
Ensure the dashboard is visually appealing and easy to understand."""
                    }
                }
            ]
        }
    
    raise ValueError(f"Unknown prompt: {name}")

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls for tracking data."""
    # Verify token before making any request
    if not client.verify_token():
        # Try to login again if token is invalid
        if not client.login(API_USERNAME, API_PASSWORD):
            raise RuntimeError("Failed to re-authenticate with Umami API")

    # Convert date strings to Unix timestamps for relevant tools
    if name in ["get_tracking_data", "get_website_stats", "get_session_ids", "get_website_metrics", "get_docs", "get_pageview_series"]:
        if "start_at" in arguments:
            arguments["start_at"] = convert_date_to_unix(arguments["start_at"], end_of_day=False)
        if "end_at" in arguments:
            arguments["end_at"] = convert_date_to_unix(arguments["end_at"], end_of_day=True)

    if name == "get_websites":
        team_id = arguments.get("team_id", TEAM_ID)
        websites = client.get_websites(team_id)
        
        if websites is None:
            raise RuntimeError("Failed to fetch websites data")

        return [
            TextContent(
                type="text",
                text=json.dumps(websites, indent=2)
            )
        ]
    
    elif name == "get_session_ids":
        # Validate required arguments
        required_args = ["website_id", "start_at", "end_at", "event_name"]
        if not all(arg in arguments for arg in required_args):
            raise ValueError(f"Missing required arguments. Need: {required_args}")
        
        if arguments["event_name"] == "None":
            include_ids = get_session_ids(arguments["website_id"], None, arguments["start_at"], arguments["end_at"])
        else:
            include_ids = get_session_ids(arguments["website_id"], arguments["event_name"], arguments["start_at"], arguments["end_at"])
        
        exclude_ids = []
            
        ids = [i for i in include_ids if i not in exclude_ids]

        return [
            TextContent(
                type="text",
                text=json.dumps(ids, indent=2)
            )
        ]
    
    elif name == "get_tracking_data":
        # Validate required arguments
        required_args = ["website_id", "start_at", "end_at", "session_id"]
        if not all(arg in arguments for arg in required_args):
            raise ValueError(f"Missing required arguments. Need: {required_args}")

        user_activity = client.get_user_activity(
            website_id=arguments["website_id"],
            session_id=arguments["session_id"]  ,
            start_at=arguments["start_at"],
            end_at=arguments["end_at"]
        )
        
        if user_activity is None:
            raise RuntimeError("Failed to fetch website statistics")

        return [
            TextContent(
                type="text",
                text=json.dumps(user_activity, indent=2)
            )
        ]
    
    elif name == "get_website_stats":
        # Validate required arguments
        required_args = ["website_id", "start_at", "end_at"]
        if not all(arg in arguments for arg in required_args):
            raise ValueError(f"Missing required arguments. Need: {required_args}")
        
        stats = client.get_website_stats(
            website_id=arguments["website_id"],
            start_at=arguments["start_at"],
            end_at=arguments["end_at"]
        )
        
        if stats is None:
            raise ValueError(f"Failed to get stats for website {arguments['website_id']}")
        
        return [
            TextContent(
                type="text",
                text=json.dumps(stats, indent=2)
            )
        ]
    
    elif name == "get_website_metrics":
        # Validate required arguments
        required_args = ["website_id", "start_at", "end_at", "type"]
        if not all(arg in arguments for arg in required_args):
            raise ValueError(f"Missing required arguments. Need: {required_args}")
        
        metrics = client.get_website_metrics(
            website_id=arguments["website_id"],
            start_at=arguments["start_at"],
            end_at=arguments["end_at"],
            type=arguments["type"]
        )
        
        return [
            TextContent(
                type="text",
                text=json.dumps(metrics, indent=2)
            )
        ]
    
    elif name == "get_docs":
        # Validate required arguments
        required_args = ["user_question", "selected_event", "website_id", "start_at", "end_at"]
        if not all(arg in arguments for arg in required_args):
            raise ValueError(f"Missing required arguments. Need: {required_args}")
        
        try:
            if arguments["selected_event"] == "None":
                include_ids = get_session_ids(arguments["website_id"], None, arguments["start_at"], arguments["end_at"])
            else:
                include_ids = get_session_ids(arguments["website_id"], arguments["selected_event"], arguments["start_at"], arguments["end_at"])
            
            exclude_ids = []
            ids = [i for i in include_ids if i not in exclude_ids]

            user_activity_list = []
            for count, session_id in enumerate(ids, 1):
                user_activity = client.get_user_activity(
                    website_id=arguments["website_id"],
                    session_id=session_id,
                    start_at=arguments["start_at"],
                    end_at=arguments["end_at"]
                )
                if user_activity:
                    user_activity_list.append(json.dumps(user_activity, indent=2))  

            docs = await get_chunks(user_activity_list, arguments["user_question"])


            # Convert docs to string format
            docs_text = "\n\n".join(doc.page_content for doc in docs)
            
            return [
                TextContent(
                    text=docs_text,  # Add the required 'text' field
                    type="text",
                    mimeType="text/plain"
                )
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get tracking data: {str(e)}")
    
    elif name == "get_screenshot":
        # Validate required arguments
        if "url" not in arguments:
            raise ValueError("Missing required argument: url")
        
        try:
            screenshot_base64 = await crawler.get_screenshot(arguments["url"])
            
            if not screenshot_base64:
                raise RuntimeError("No screenshot data returned")
                
            return [
                ImageContent(
                    type="image",
                    mimeType="image/jpeg",
                    data=screenshot_base64
                )
            ]
        except TimeoutError as e:
            raise RuntimeError(f"Screenshot timed out: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Failed to get screenshot: {str(e)}")
    
    elif name == "get_html":
        # Validate required arguments
        if "url" not in arguments:
            raise ValueError("Missing required argument: url")
        
        try:
            html = await crawler.get_html(arguments["url"])
            return [
                TextContent(
                    type="text",
                    text=html
                )
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get html: {str(e)}") 
    
    elif name == "get_pageview_series":
        # Validate required arguments
        required_args = ["website_id", "start_at", "end_at", "unit", "timezone"]
        if not all(arg in arguments for arg in required_args):
            raise ValueError(f"Missing required arguments. Need: {required_args}")
        
        pageview_series = client.get_pageview_series(
            website_id=arguments["website_id"],
            start_at=arguments["start_at"],
            end_at=arguments["end_at"],
            unit=arguments["unit"],
            timezone=arguments["timezone"]
        )
        
        if pageview_series is None:
            raise ValueError(f"Failed to get pageview series for website {arguments['website_id']}")
        
        return [
            TextContent(
                type="text",
                text=json.dumps(pageview_series, indent=2)
            )
        ]
    
    elif name == "get_active_visitors":
        # Validate required arguments
        if "website_id" not in arguments:
            raise ValueError("Missing required argument: website_id")
        
        active_data = client.get_active(
            website_id=arguments["website_id"]
        )
        
        if active_data is None:
            raise ValueError(f"Failed to get active visitor data for website {arguments['website_id']}")
        
        return [
            TextContent(
                type="text",
                text=json.dumps(active_data, indent=2)
            )
        ]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        ) 