from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import UserSerializer


@api_view(["GET"])
def me(request):
    """Return the currently logged-in user (used by the React app after login)."""
    return Response(UserSerializer(request.user).data)
