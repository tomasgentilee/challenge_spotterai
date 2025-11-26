from django.urls import path
from . import views

urlpatterns = [
    path("route/coordinates/", views.generate_route, name="get_coordinates"),
]