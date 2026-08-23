from typing import TYPE_CHECKING, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import QuerySet
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from trips.forms import TripForm
from trips.models import Trip

if TYPE_CHECKING:
    _TripListViewBase = ListView[Trip]
    _TripCreateViewBase = CreateView[Trip, TripForm]
    _SuccessMessageMixinBase = SuccessMessageMixin[TripForm]
else:
    _TripListViewBase = ListView
    _TripCreateViewBase = CreateView
    _SuccessMessageMixinBase = SuccessMessageMixin


class TripListView(LoginRequiredMixin, _TripListViewBase):
    """Lists the requesting user's own trips."""

    def get_queryset(self) -> QuerySet[Trip]:
        return Trip.objects.filter(owner=cast(User, self.request.user))


class TripCreateView(LoginRequiredMixin, _SuccessMessageMixinBase, _TripCreateViewBase):
    """Creates a trip owned by the requesting user."""

    form_class = TripForm
    template_name = "trips/trip_form.html"
    success_url = reverse_lazy("trips:list")
    success_message = "Trip saved."

    def form_valid(self, form: TripForm) -> HttpResponse:
        form.instance.owner = cast(User, self.request.user)
        return super().form_valid(form)
