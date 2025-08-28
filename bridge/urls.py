from .views import *
from django.urls import path

urlpatterns = [
    path('test', TestView.as_view()),
    path('account/create', CreateAccountView.as_view()),
]
