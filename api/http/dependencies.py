from fastapi import Request

from internal.container import ServiceContainer


def get_services(request: Request) -> ServiceContainer:
    return request.app.state.services
