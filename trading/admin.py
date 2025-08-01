from django.contrib import admin
from .models import *

admin.site.register(TradingAccount)
admin.site.register(Trade)
admin.site.register(AccountActivity)
admin.site.register(DailyAccountStats)
admin.site.register(UserProfile)
# Register your models here.
