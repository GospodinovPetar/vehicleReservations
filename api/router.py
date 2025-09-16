from ninja import NinjaAPI
from .auth import BasicAuth
from .endpoints import register_routes

basic_auth = BasicAuth()

api = NinjaAPI(
    title="Vehicle Reservations API",
    version="1.0.0",
    description="Use the Authorize button with username + password (HTTP Basic).",
    auth=basic_auth,
    csrf=False,
)

register_routes(api)
