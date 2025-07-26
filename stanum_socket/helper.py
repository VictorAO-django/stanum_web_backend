from account.serializers import *
from account.models import *
from decimal import Decimal
import json

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)  # convert Decimal to string to keep precision
        return super().default(obj)