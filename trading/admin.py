from django.contrib import admin
from .models import *

admin.site.register(MT5User)
admin.site.register(MT5Account)
admin.site.register(MT5Daily)
admin.site.register(MT5Deal)
admin.site.register(MT5Order)
admin.site.register(MT5Position)
admin.site.register(MT5OrderHistory)
admin.site.register(MT5Summary)
admin.site.register(MT5UserLoginHistory)

admin.site.register(RuleViolationLog)
admin.site.register(SymbolPrice)
# Register your models here.
