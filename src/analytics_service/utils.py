from datetime import datetime


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
        raise ValueError(
            f"Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS. Error: {str(e)}"
        )
