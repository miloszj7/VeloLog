from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView

from accounts.forms import SignUpForm

if TYPE_CHECKING:
    _SignUpViewBase = CreateView[User, SignUpForm]
else:
    _SignUpViewBase = CreateView


class SignUpView(_SignUpViewBase):
    """Registration view that creates a new user via SignUpForm."""

    form_class = SignUpForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy(settings.LOGIN_REDIRECT_URL)

    def form_valid(self, form: SignUpForm) -> HttpResponse:
        """Create the user, then log them in immediately."""
        response = super().form_valid(form)
        login(self.request, self.object)
        return response
