from contextlib import asynccontextmanager
import logging
import os
import json

from dotenv import load_dotenv
import httpx
from mcp.types import TextContent, PromptMessage
from mcp.server.fastmcp import FastMCP

from analytics_service.utils import convert_date_to_unix
from analytics_service.api import UmamiClient

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("umami_mcp_server")

httpx_client = httpx.AsyncClient()


@asynccontextmanager
async def lifespan(app: FastMCP):
    """
    Context manager to ensure the shared httpx client is closed when the server stops.

    Args:
        app (FastMCP): The MCP server application instance.
    """
    try:
        yield
    finally:
        await httpx_client.aclose()


mcp = FastMCP("umami", lifespan=lifespan)

# API configuration
API_BASE_URL = os.getenv("UMAMI_API_URL") or "https://api.umami.is/v1"  # cloud
API_USERNAME = os.getenv("UMAMI_USERNAME")
API_PASSWORD = os.getenv("UMAMI_PASSWORD")
TEAM_ID = os.getenv("UMAMI_TEAM_ID")

API_KEY = os.getenv("UMAMI_API_KEY")

client = UmamiClient(API_BASE_URL)

if API_KEY:
    client.set_api_token(API_KEY)
elif API_USERNAME and API_PASSWORD and TEAM_ID:
    if not client.login(API_USERNAME, API_PASSWORD):
        raise RuntimeError("Failed to login to Umami API")
else:
    raise ValueError("Missing required environment variables")


def _get_session_ids(website_id, event_name, start_at, end_at):
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
            page_size=200,
        )
        if not events_where:
            break

        if events_where:
            db = list({event["sessionId"] for event in events_where["data"]})
            for i in db:
                ids.append(i)
        if 200 * events_where["page"] >= events_where["count"]:
            break
        else:
            page += 1
    return list(set(ids))


@mcp.prompt()
async def create_dashboard(
    website_name: str,
    start_date: str,
    end_date: str,
    timezone: str,
):
    """Guide for creating comprehensive analytics dashboards using website metrics and stats

    Args:
    - website_name: Name of the website to analyze
    - start_date: Start date for analysis (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
    - end_date: End date for analysis (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
    - timezone: Timezone for the analysis (e.g., 'UTC', 'Europe/London')

    """
    content = f"""You are an analytics expert helping to create a comprehensive dashboard using website tracking data. 
Follow these steps to create an attractive and engaging dashboard for website: {website_name}, analyzing data from {start_date} to {end_date} in timezone {timezone}.
To begin, get the website id using get_websites and find the id of the website with the name {website_name}. Then use the id to get the other data.

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
    return PromptMessage(role="user", content=TextContent(type="text", text=content))


@mcp.tool()
async def get_websites() -> str:
    """Retrieve a list of the websites present in the tracking database.

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
    """
    try:
        sites = client.get_websites()
        return json.dumps(sites, indent=2)
    except Exception as e:
        logger.error("get_websites error: %s", e)
        return f"Error fetching websites: {e}"


@mcp.tool()
async def get_session_ids(
    website_id: str,
    start_at: str,
    end_at: str,
    event_name: str | None = None,
) -> str:
    """Get a list of the unique session IDs who visited a specific website within a time range and perform a specific event.

    WARNING: due to api limitations, only the first 1000 total session IDs will be returned by the api. Within those less will be unique.
    Do not use this tool to calculate the number of unique visitors - only use it to get session IDs.

    Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.

    Args
        - website_id (string): The ID of the website where the user journey is located
        - start_at (string): Start date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 00:00:00
            - 2024-01-31
            Note: If time is not provided, 00:00:00 will be used
        - end_at (string): End date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 23:59:59
            - 2024-01-31
            Note: If time is not provided, 23:59:59.999 will be used
        - event_name (string): Name of the event to filter by. Here are the possible events:
            - product_details_viewed
            - product_clicked
            - user_sign_in
            - product_added_to_cart
            - checkout_started
            - language_changed
            - checkout_completed
            If not filtering by an event, set this to None.
    """
    try:
        start_ts = convert_date_to_unix(start_at, end_of_day=False)
        end_ts = convert_date_to_unix(end_at, end_of_day=True)
        ids = _get_session_ids(website_id, event_name, start_ts, end_ts)
        return json.dumps(ids, indent=2)
    except Exception as e:
        logger.error("get_session_ids error: %s", e)
        return f"Error fetching session IDs: {e}"


@mcp.tool()
async def get_tracking_data(
    website_id: str,
    session_id: str,
    start_at: str,
    end_at: str,
) -> str:
    """Get the user journey for a specific session ID within a time range.
    Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided

    Args:
        - website_id (string): The ID of the website where the user journey is located
        - start_at (string): Start date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 00:00:00
            - 2024-01-31
            Note: If time is not provided, 00:00:00 will be used
        - end_at (string): End date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 23:59:59
            - 2024-01-31
            Note: If time is not provided, 23:59:59.999 will be used
        - session_id (string): ID of the user session to get tracking data for
    """
    try:
        start_ts = convert_date_to_unix(start_at, end_of_day=False)
        end_ts = convert_date_to_unix(end_at, end_of_day=True)
        data = client.get_user_activity(
            website_id=website_id,
            session_id=session_id,
            start_at=start_ts,
            end_at=end_ts,
        )
        return json.dumps(data, indent=2)
    except Exception as e:
        logger.error("get_tracking_data error: %s", e)
        return f"Error fetching tracking data: {e}"


@mcp.tool()
async def get_website_stats(
    website_id: str,
    start_at: str,
    end_at: str,
) -> str:
    """Get the 5 overivew metrics for a specific website within a time range.

    The returned metrics are as follows:
        - pageviews: The number of total pageviews for the entire website
        - visitors: The number of unique visitors the website has had
        - visits: The number of unique visits those visitors have had to the website
        - bounces: The number of visitors that left the website without interacting with it
        - totaltime: The total time spent on the website by all visitors

    Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.

    Args
        - website_id (string): The ID of the website where the user journey is located
        - start_at (string): Start date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 00:00:00
            - 2024-01-31
            Note: If time is not provided, 00:00:00 will be used
        - end_at (string): End date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 23:59:59
            - 2024-01-31
            Note: If time is not provided, 23:59:59.999 will be used
    """
    try:
        start_ts = convert_date_to_unix(start_at, end_of_day=False)
        end_ts = convert_date_to_unix(end_at, end_of_day=True)
        stats = client.get_website_stats(
            website_id=website_id,
            start_at=start_ts,
            end_at=end_ts,
        )
        return json.dumps(stats, indent=2)
    except Exception as e:
        logger.error("get_website_stats error: %s", e)
        return f"Error fetching website stats: {e}"


@mcp.tool()
async def get_website_metrics(
    website_id: str,
    start_at: str,
    end_at: str,
    type: str,
) -> str:
    """Get various metrics for a specific website within a time range and how many visitors have had each metric.
    The metric type is selected by type property.

    Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.

    Args
        - website_id (string): The ID of the website where the user journey is located
        - start_at (string): Start date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 00:00:00
            - 2024-01-31
            Note: If time is not provided, 00:00:00 will be used
        - end_at (string): End date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 23:59:59
            - 2024-01-31
            Note: If time is not provided, 23:59:59.999 will be used
        - type (string): Type of metrics to retrieve. Here are the possible types:
            - url: The number of visits for each URL on the website (effectively the number times each page has been visited)
            - referrer: Where the visitors came from to get to the website
            - browser: Which browser the visitors used to visit the website
            - os: Which operating system the visitors used to visit the website
            - device: Which device the visitors used to visit the website
            - country: Which country the visitors are from
            - event: The tally of each event that has occurred on the website
    """
    try:
        start_ts = convert_date_to_unix(start_at, end_of_day=False)
        end_ts = convert_date_to_unix(end_at, end_of_day=True)
        metrics = client.get_website_metrics(
            website_id=website_id,
            start_at=start_ts,
            end_at=end_ts,
            type=type,
        )
        return json.dumps(metrics, indent=2)
    except Exception as e:
        logger.error("get_website_metrics error: %s", e)
        return f"Error fetching website metrics: {e}"


# @mcp.tool()
# async def get_docs(
#     user_question: str,
#     selected_event: str | None,
#     website_id: str,
#     start_at: str,
#     end_at: str,
# ) -> str:
#     """Performs the document selection and retrieval part of the RAG pipeline for user journeys from umami tracking data.
#     User journey data is retrieved for all users who performed the selected event. Then the data is then chunked into documents and embedded into a vector database.
#     Similarity search based of the users question is then used to retrieve the most relevant documents. These documents are returned for use in answering the user's question.

#     Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.

#     Args
#         - user_question (string): The user's question to be used to retrieve relevant documents. This does not have to be word for word the same as the question the user asked, but should allow for the most relevant documents to be retrieved.
#         - selected_event (string): The event to filter the session ids by. Here are the possible events:
#             - product_details_viewed
#             - product_clicked
#             - user_sign_in
#             - product_added_to_cart
#             - checkout_started
#             - language_changed
#             - checkout_completed
#             If not filtering by an event, set this to None.
#         - website_id (string): The ID of the website where the user journey is located
#         - start_at (string): Start date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
#             Examples:
#             - 2024-03-01
#             - 2024-03-01 00:00:00
#             - 2024-01-31
#             Note: If time is not provided, 00:00:00 will be used
#         - end_at (string): End date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
#             Examples:
#             - 2024-03-01
#             - 2024-03-01 23:59:59
#             - 2024-01-31
#             Note: If time is not provided, 23:59:59.999 will be used
#     """
#     try:
#         # convert dates
#         start_ts = convert_date_to_unix(start_at, end_of_day=False)
#         end_ts = convert_date_to_unix(end_at, end_of_day=True)
#         # fetch sessions
#         sessions = _get_session_ids(
#             website_id,
#             None if selected_event in (None, "None") else selected_event,
#             start_ts,
#             end_ts,
#         )
#         # gather activity json strings
#         activities = []
#         for sid in sessions:
#             act = client.get_user_activity(
#                 website_id=website_id,
#                 session_id=sid,
#                 start_at=start_ts,
#                 end_at=end_ts,
#             )
#             if act:
#                 activities.append(json.dumps(act, indent=2))
#         # chunk & embed
#         docs = await get_chunks(activities, user_question)
#         return "\n\n".join(d.page_content for d in docs)
#     except Exception as e:
#         logger.error("get_docs error: %s", e)
#         return f"Error building docs: {e}"


@mcp.tool()
async def get_pageview_series(
    website_id: str,
    start_at: str,
    end_at: str,
    unit: str,
    timezone: str,
) -> str:
    """Get the pageview data series for a specific website within a time range.
    The data is grouped by the specified time unit (hour, day, month) and includes the number
    of pageviews and sessions for each time period.

    Note: If no results are returned, do not immediately assume there is no data - verify the unix timestamps are correct and ask the user for specific date ranges if not provided.

    Args
        - website_id (string): The ID of the website where the user journey is located
        - start_at (string): Start date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 00:00:00
            - 2024-01-31
            Note: If time is not provided, 00:00:00 will be used
        - end_at (string): End date for time range of data to retrieve. Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            Examples:
            - 2024-03-01
            - 2024-03-01 23:59:59
            - 2024-01-31
            Note: If time is not provided, 23:59:59.999 will be used
        - unit (string): Time unit for grouping data (hour, day, or month)
        - timezone (string): Timezone for the data (e.g., 'UTC', 'Europe/London')
    """
    try:
        start_ts = convert_date_to_unix(start_at, end_of_day=False)
        end_ts = convert_date_to_unix(end_at, end_of_day=True)
        series = client.get_pageview_series(
            website_id=website_id,
            start_at=start_ts,
            end_at=end_ts,
            unit=unit,
            timezone=timezone,
        )
        return json.dumps(series, indent=2)
    except Exception as e:
        logger.error("get_pageview_series error: %s", e)
        return f"Error fetching pageview series: {e}"


@mcp.tool()
async def get_active_visitors(website_id: str) -> str:
    """Get the current number of active visitors on a specific website.
    This provides real-time data about how many visitors are currently on the website.

    Args
        - website_id (string): ID of the website to get active visitor data for
    """
    try:
        data = client.get_active(website_id)
        return json.dumps(data, indent=2)
    except Exception as e:
        logger.error("get_active_visitors error: %s", e)
        return f"Error fetching active visitors: {e}"


if __name__ == "__main__":
    mcp.run()
