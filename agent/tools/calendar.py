from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Optional

from langchain_core.tools import tool

if TYPE_CHECKING:
    from agent.config import AgentConfig


def _get_caldav_calendar(config: "AgentConfig"):
    """Return the default CalDAV calendar object."""
    import caldav
    if not config.caldav_url:
        raise RuntimeError("Calendar not configured. Set CALDAV_URL.")
    client = caldav.DAVClient(url=config.caldav_url)
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        raise RuntimeError("No calendars found at CalDAV URL.")
    return calendars[0]


def _parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: '{s}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM.")


def _event_summary(vevent) -> str:
    try:
        uid = str(vevent.get("uid", ""))
        summary = str(vevent.get("summary", ""))
        dtstart = vevent.get("dtstart")
        dtend = vevent.get("dtend")
        location = str(vevent.get("location", ""))
        start_str = str(dtstart.dt) if dtstart else "?"
        end_str = str(dtend.dt) if dtend else "?"
        return f"ID:{uid} | {start_str} → {end_str} | {summary}" + (f" @ {location}" if location else "")
    except Exception:
        return "(unreadable event)"


def create_calendar_tools(config: "AgentConfig") -> list:

    @tool
    def calendar_list(start: str, end: str) -> str:
        """List calendar events in a date range.

        Args:
            start: Start date in YYYY-MM-DD format.
            end: End date in YYYY-MM-DD format.
        """
        try:
            cal = _get_caldav_calendar(config)
            from datetime import date
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            events = cal.date_search(start=start_dt, end=end_dt)
            if not events:
                return "No events found in that range."
            lines = []
            for ev in events:
                vevent = ev.vobject_instance.vevent
                lines.append(_event_summary(vevent))
            return "\n".join(lines)
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def calendar_get(event_id: str) -> str:
        """Get the full details of a single calendar event.

        Args:
            event_id: The UID of the event (as shown by calendar_list).
        """
        try:
            cal = _get_caldav_calendar(config)
            event = cal.event_by_uid(event_id)
            vevent = event.vobject_instance.vevent
            props = {
                "uid": str(vevent.get("uid", "")),
                "summary": str(vevent.get("summary", "")),
                "start": str(vevent.get("dtstart").dt) if vevent.get("dtstart") else "",
                "end": str(vevent.get("dtend").dt) if vevent.get("dtend") else "",
                "location": str(vevent.get("location", "")),
                "description": str(vevent.get("description", "")),
                "attendees": [str(a) for a in vevent.contents.get("attendee", [])],
            }
            return json.dumps(props, indent=2, ensure_ascii=False)
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def calendar_create(
        title: str,
        start: str,
        end: str,
        attendees: Optional[List[str]] = None,
        location: Optional[str] = None,
    ) -> str:
        """Create a new calendar event.

        Args:
            title: Event title/summary.
            start: Start time in YYYY-MM-DDTHH:MM format.
            end: End time in YYYY-MM-DDTHH:MM format.
            attendees: Optional list of attendee email addresses.
            location: Optional location string.
        """
        try:
            cal = _get_caldav_calendar(config)
            uid = str(uuid.uuid4())
            start_dt = _parse_dt(start)
            end_dt = _parse_dt(end)

            ical_lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//OfficeAgent//EN",
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"SUMMARY:{title}",
                f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            ]
            if location:
                ical_lines.append(f"LOCATION:{location}")
            if attendees:
                for att in attendees:
                    ical_lines.append(f"ATTENDEE:mailto:{att}")
            ical_lines += ["END:VEVENT", "END:VCALENDAR"]
            ical_str = "\r\n".join(ical_lines) + "\r\n"
            cal.add_event(ical_str)
            return f"Event created: {title} (UID: {uid})"
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def calendar_update(
        event_id: str,
        title: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        location: Optional[str] = None,
    ) -> str:
        """Update fields of an existing calendar event. Only pass fields you want to change.

        Args:
            event_id: The UID of the event.
            title: New title/summary.
            start: New start time (YYYY-MM-DDTHH:MM).
            end: New end time (YYYY-MM-DDTHH:MM).
            attendees: Replacement attendee list.
            location: New location.
        """
        try:
            cal = _get_caldav_calendar(config)
            event = cal.event_by_uid(event_id)
            vevent = event.vobject_instance.vevent

            if title is not None:
                vevent.summary.value = title
            if start is not None:
                vevent.dtstart.value = _parse_dt(start)
            if end is not None:
                vevent.dtend.value = _parse_dt(end)
            if location is not None:
                if hasattr(vevent, "location"):
                    vevent.location.value = location
                else:
                    vevent.add("location").value = location
            if attendees is not None:
                # Remove existing, add new
                for att in list(vevent.contents.get("attendee", [])):
                    vevent.contents["attendee"].remove(att)
                for att in attendees:
                    vevent.add("attendee").value = f"mailto:{att}"

            event.save()
            return f"Event {event_id} updated."
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def calendar_delete(event_id: str, confirm: bool = False) -> str:
        """Delete a calendar event. Requires confirm=True to actually delete.

        Args:
            event_id: The UID of the event to delete.
            confirm: Must be True to perform the deletion.
        """
        if not confirm:
            return json.dumps({
                "status": "pending_confirmation",
                "message": f"About to delete event {event_id}. Call again with confirm=True to proceed.",
            })
        try:
            cal = _get_caldav_calendar(config)
            event = cal.event_by_uid(event_id)
            event.delete()
            return f"Event {event_id} deleted."
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def calendar_find_slot(
        duration_minutes: int,
        attendees: List[str],
        within_days: int = 7,
    ) -> str:
        """Find free time slots for a meeting within the next N days.

        Args:
            duration_minutes: Required meeting duration in minutes.
            attendees: List of attendee email addresses.
            within_days: How many days ahead to search (default: 7).
        """
        try:
            cal = _get_caldav_calendar(config)
            now = datetime.now().replace(second=0, microsecond=0)
            end_range = now + timedelta(days=within_days)
            events = cal.date_search(start=now, end=end_range)

            # Build list of busy intervals
            busy: list[tuple[datetime, datetime]] = []
            for ev in events:
                try:
                    vevent = ev.vobject_instance.vevent
                    ds = vevent.dtstart.value
                    de = vevent.dtend.value
                    # Convert date to datetime if needed
                    if not isinstance(ds, datetime):
                        ds = datetime(ds.year, ds.month, ds.day)
                    if not isinstance(de, datetime):
                        de = datetime(de.year, de.month, de.day)
                    busy.append((ds, de))
                except Exception:
                    pass

            busy.sort()

            # Search 9am-6pm each day
            slots = []
            current = now.replace(hour=9, minute=0)
            duration = timedelta(minutes=duration_minutes)

            while current < end_range and len(slots) < 5:
                slot_end = current + duration
                if slot_end.hour > 18:
                    current = (current + timedelta(days=1)).replace(hour=9, minute=0)
                    continue
                if current.weekday() >= 5:  # skip weekends
                    current = (current + timedelta(days=1)).replace(hour=9, minute=0)
                    continue
                # Check for conflicts
                conflict = any(bs < slot_end and be > current for bs, be in busy)
                if not conflict:
                    slots.append(f"{current.strftime('%Y-%m-%d %H:%M')} – {slot_end.strftime('%H:%M')}")
                current += timedelta(minutes=30)

            if not slots:
                return "No free slots found in the search window."
            return "Available slots:\n" + "\n".join(slots)
        except Exception as exc:
            return f"Error: {exc}"

    return [calendar_list, calendar_get, calendar_create, calendar_update, calendar_delete, calendar_find_slot]
