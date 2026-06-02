import os
import re
from datetime import datetime
from pathlib import Path

from prefect import task
from prefect.logging import get_run_logger

from research_agent import run_agent_sync
from sql_utils import get_db
from tables import EventList, Events, Towns, Weekends

os.environ["SERPAPI_API_KEY"] = os.getenv("SERPAPI_API_KEY", "your_serpapi_key_here")

from langchain_community.tools.google_trends.tool import GoogleTrendsQueryRun
from langchain_community.utilities.google_trends import GoogleTrendsAPIWrapper


def check_events(events_list: list):
    """
    Checks the event list, ensuring that there are at least 5 events and that each event has the required fields (event_name, event_time, event_description) populated. If a location is provided, it checks for the presence of location_name and location_address, and validates the format of the location_address and event_time. It returns a message indicating any issues found with the events or "success" if all events are appropriately matched.

    Args:
        events_list (list): The list of dict events to check. Example [{ "event_name": "Test Event", "time": "afasdfda", "description": "This is a test event.", "location_address": "123 Main St, City, ST 12345", "date": "2026-05-1ada6"}]

    Returns:
        str: A message indicating whether there is at least 5 events and that the values are correctly populated. Returns "success" if all events are appropriately matched.
    """
    print(f"Checking events for {events_list}...")

    if not events_list:
        return "You provided an empty value. No events to check."

    if len(events_list) < 5:
        return (
            f"You provided only {len(events_list)} events. Please provide at least 5"
            " events."
        )

    res = ""

    def validate_time(time_string, time_format):
        try:
            # Attempts to parse the string into a datetime object
            datetime.strptime(time_string, time_format)
            return True
        except ValueError:
            # If parsing fails, the format is incorrect
            return False

    def validate_date(date_string, date_format):
        try:
            # Tries to parse the string using the format
            datetime.strptime(date_string, date_format)
            return True
        except ValueError:
            # Returns False if parsing fails (wrong format or invalid date like Feb 30)
            return False

    for event in events_list:
        if (
            not event["event_name"]
            or not event["date"]
            or not event["time"]
            or not event["description"]
        ):

            res = (
                res
                + f"Event {event['event_name']} is missing required fields. Please"
                " ensure all events have an event_name, event_time, and"
                " event_description."
            )
            res = res + "\n"

        if not event["location_address"]:
            res = (
                res
                + f"Event {event['event_name']} has a location provided but is missing"
                " location_name or location_address. Please ensure that if a"
                " location address is provided."
            )
            res = res + "\n"

        address_pattern = r"^\d+\s[A-z0-9\s]+,\s[A-z\s]+,\s[A-Z]{2}\s\d{5}$"

        if not re.match(address_pattern, event["location_address"]):
            res = (
                res
                + f"Event {event['event_name']} has an invalid location address format."
                " Please ensure the address follows the format: '123 Main St, City,"
                " ST 12345'."
            )
            res = res + "\n"

        if not validate_time(event["time"], "%I:%M %p"):
            res = (
                res
                + f"Event {event['event_name']} has an invalid event time format."
                " Please ensure the time follows the format: '7:00 PM'."
            )
            res = res + "\n"

        if not validate_date(event["date"], "%Y-%m-%d"):
            res = (
                res
                + f"Event {event['event_name']} has an invalid event date format."
                " Please ensure the date follows the format: 'YYYY-MM-DD'."
            )
            res = res + "\n"

        if len(event["keywords"].split(",")) <= 1:
            res = (
                res
                + f"Event {event['event_name']} is missing keywords or you only"
                " provided one keyword. Please provide keywords that are trending"
                " for this event based on your research as a comma separated list."
            )
            res = res + "\n"

    if not res:
        res = "success"

    return res


def populate_db_with_events(event_list: EventList, town_id: int, weekend_id: int):

    session = next(get_db())
    logger = get_run_logger()

    event_id_list = []

    if len(event_list.events) == 0:
        logger.info(
            "No events to add for town_id %s and weekend_id %s", town_id, weekend_id
        )
        raise ValueError("No events to add to the database.")

    for new_event in event_list.events:
        logger.info("Adding the event %s", new_event.event_name)
        new_event_sql = Events(**new_event.__dict__)
        new_event_sql.town_id = town_id
        new_event_sql.weekend_id = weekend_id
        session.add(new_event_sql)
        session.commit()
        event_id_list.append(new_event_sql.id)

    session.close()

    return event_id_list


@task(
    task_run_name="event_research_agent-{town_id}-{weekend_id}",
    retries=3,
    retry_delay_seconds=10,
)
def main(town_id=0, weekend_id=0):

    logger = get_run_logger()
    session = next(get_db())

    w = session.query(Weekends).filter(Weekends.id == weekend_id).first()
    t = session.query(Towns).filter(Towns.id == town_id).first()

    trends_wrapper = GoogleTrendsAPIWrapper()
    trends_tool = GoogleTrendsQueryRun(api_wrapper=trends_wrapper)
    trends_tools_str = "GoogleTrendsQueryRun"

    event_list = run_agent_sync(
        user_prompt_params={
            "town_name": t.name,
            "town_state": t.state,
            "weekend_date": w.date,
        },
        system_prompt_params={"num_events": 5, "trends_tools_str": trends_tools_str},
        ReturnClass=EventList,
        prompt_dir=Path(__file__).parent.resolve(),
        extra_tools=[check_events, trends_tool],
    )
    event_id_list = populate_db_with_events(
        event_list, town_id=town_id, weekend_id=weekend_id
    )

    return event_id_list


if __name__ == "__main__":
    print(
        check_events(
            events_list=5
            * [
                {
                    "event_name": "Test Event",
                    "time": "afasdfda",
                    "description": "This is a test event.",
                    "location_address": "123 Main St, City, ST 12345",
                    "date": "2026-05-1ada6",
                }
            ]
        )
    )
