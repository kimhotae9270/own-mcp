from googleapiclient.discovery import build


class CalendarService:

    def __init__(self, creds):
        self.service = build("calendar", "v3", credentials=creds)

    def create_event(self, summary, start, end):

        event = {
            "summary": summary,
            "start": {"dateTime": start, "timeZone": "Asia/Seoul"},
            "end": {"dateTime": end, "timeZone": "Asia/Seoul"},
        }

        created = self.service.events().insert(
            calendarId="primary",
            body=event
        ).execute()

        return created["id"], created["htmlLink"]

    def list_events(self, max_results=10):

        events_result = self.service.events().list(
            calendarId="primary",
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        return events_result.get("items", [])

    def delete_event(self, event_id):

        self.service.events().delete(
            calendarId="primary",
            eventId=event_id
        ).execute()

        return True

    def update_event(self, event_id, summary=None):

        event = self.service.events().get(
            calendarId="primary",
            eventId=event_id
        ).execute()

        if summary:
            event["summary"] = summary

        updated = self.service.events().update(
            calendarId="primary",
            eventId=event_id,
            body=event
        ).execute()

        return updated["htmlLink"]
