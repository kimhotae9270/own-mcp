from fastmcp import FastMCP,Context
import token_service
from CalendarService import CalendarService

def register_calendar_tools(mcp: FastMCP):

    @mcp.tool
    def create_event(ctx: Context, summary: str, start: str, end: str):

        creds = token_service.get_google_creds(ctx.user_id)

        calendar = CalendarService(creds)

        event_id, link = calendar.create_event(summary, start, end)

        return {
            "event_id": event_id,
            "link": link
        }


    @mcp.tool
    def list_events(ctx: Context):

        creds = token_service.get_google_creds(ctx.user_id)

        calendar = CalendarService(creds)

        return calendar.list_events()


    @mcp.tool
    def delete_event(ctx: Context, event_id: str):

        creds = token_service.get_google_creds(ctx.user_id)

        calendar = CalendarService(creds)

        calendar.delete_event(event_id)

        return "deleted"


    @mcp.tool
    def update_event(ctx: Context, event_id: str, summary: str):

        creds = token_service.get_google_creds(ctx.user_id)

        calendar = CalendarService(creds)

        return calendar.update_event(event_id, summary)

