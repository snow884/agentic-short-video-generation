import re
from datetime import datetime
from pathlib import Path

from prefect import task
from prefect.logging import get_run_logger

from research_agent import run_agent_sync
from sql_utils import get_db
from tables import Base, EventList, Events, Towns, Weekends


def check_events(events_list: list):
    """
    Checks the event list, ensuring that there are at least 5 events and that each event has the required fields (event_name, event_time, event_description) populated. If a location is provided, it checks for the presence of location_name and location_address, and validates the format of the location_address and event_time. It returns a message indicating any issues found with the events or "success" if all events are appropriately matched.

    Args:
        events_list (list): The list of events to check.

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

    for event in events_list:
        if not event.event_name or not event.event_time or not event.event_description:
            res = (
                res
                + f"Event {event} is missing required fields. Please ensure all events"
                " have an event_name, event_time, and event_description."
            )
            res = res + "\n"

        if not event.location_address:
            res = (
                res
                + f"Event {event} has a location provided but is missing location_name"
                " or location_address. Please ensure that if a location address is"
                " provided."
            )
            res = res + "\n"

        address_pattern = r"^\d+\s[A-z0-9\s]+,\s[A-z\s]+,\s[A-Z]{2}\s\d{5}$"

        if not re.match(address_pattern, event.location_address):
            res = (
                res
                + f"Event {event} has an invalid location address format. Please ensure"
                " the address follows the format: '123 Main St, City, ST 12345'."
            )
            res = res + "\n"

        if not validate_time(event.event_time, "%I:%M %p"):
            res = (
                res
                + f"Event {event} has an invalid event time format. Please ensure the"
                " time follows the format: '7:00 PM'."
            )
            res = res + "\n"

    if not res:
        res = "success"

    return res


def populate_db_with_events(event_list: EventList, town_id: int, weekend_id: int):

    session = next(get_db())
    logger = get_run_logger()

    event_id_list = []

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


@task(task_run_name="event_research_agent-{town_id}-{weekend_id}")
def main(town_id=0, weekend_id=0):

    logger = get_run_logger()
    session = next(get_db())

    w = session.query(Weekends).filter(Weekends.id == weekend_id).first()
    t = session.query(Towns).filter(Towns.id == town_id).first()

    event_list = run_agent_sync(
        user_prompt_params={
            "town_name": t.name,
            "town_state": t.state,
            "weekend_date": w.date,
        },
        system_prompt_params={"num_events": 5},
        ReturnClass=EventList,
        prompt_dir=Path(__file__).parent.resolve(),
        extra_tools=[check_events],
    )
    event_id_list = populate_db_with_events(
        event_list, town_id=town_id, weekend_id=weekend_id
    )

    return event_id_list


if __name__ == "__main__":
    from dotenv import load_dotenv
    from sqlalchemy import create_engine

    engine = create_engine(
        "sqlite:///data/local.db", echo=False
    )  # echo=True shows SQL logs

    load_dotenv()

    def create_tables():

        Base.metadata.create_all(engine)

    create_tables()

    main(town_id=1, weekend_id=1)
