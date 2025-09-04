
from django.db.models import Min, Avg
import django_filters
from django.db.models import Q

from payment.models import *
from challenge.models import *

class PropFirmWalletTransactionFilter(django_filters.FilterSet):
    # Date filters
    date_after = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    date_before = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )

    # Amount filters
    amount_min = django_filters.NumberFilter(
        field_name="requested_amount", lookup_expr="gte"
    )
    amount_max = django_filters.NumberFilter(
        field_name="requested_amount", lookup_expr="lte"
    )

    # Status filter
    status = django_filters.CharFilter(
        field_name="status", lookup_expr="iexact"
    )

    # Type filter
    type = django_filters.CharFilter(
        field_name="type", lookup_expr="iexact"
    )

    class Meta:
        model = PropFirmWalletTransaction
        fields = [
            "date_after",
            "date_before",
            "amount_min",
            "amount_max",
            "status",
            "type",
        ]


class PropFirmChallengeFilter(django_filters.FilterSet):
    challenge_class = django_filters.CharFilter(field_name='challenge_class', lookup_expr='iexact')
    class Meta:
        model =  PropFirmChallenge
        fields = ['challenge_class']