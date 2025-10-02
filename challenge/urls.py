from .views import *
from django.urls import path

urlpatterns = [
    path('', PropFirmChallengeListView.as_view()),
    path('<int:id>', PropFirmChallengeDetailView.as_view()),
    path('balance', BalanceListView.as_view()),

    path('certificates', ChallengeCertificateView.as_view()),
    path('contest/<uuid:uuid>/is-a-participant', IsAParticipantView.as_view()),
    path('contest/<uuid:uuid>', CompetitionView.as_view()),
    path('contest/<uuid:uuid>/result', CompetitionResultView.as_view()),
]