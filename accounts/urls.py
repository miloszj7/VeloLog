from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("landing/", views.landing, name="landing"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
]
