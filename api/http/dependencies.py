from starlette.requests import HTTPConnection

from internal.container import ServiceContainer


def get_services(connection: HTTPConnection) -> ServiceContainer:
    return connection.app.state.services
