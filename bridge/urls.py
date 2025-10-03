from .views import *
from django.urls import path

urlpatterns = [
    path('test', TestView.as_view()),
    path('account/create', CreateAccountView.as_view()),

    path('dispatch-account-challenge', DispatchAccountChallenge.as_view()),
    
    path('dispatch-competition/<uuid:uuid>', DispatchAccountCompetition.as_view()),
    path('end-competiton/<uuid:uuid>', EndCompetitionView.as_view()),
]
