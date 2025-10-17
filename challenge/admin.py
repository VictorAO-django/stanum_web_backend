from django.contrib import admin
from .models import *

class CompetitionAdmin(admin.ModelAdmin):
    readonly_fields=['uuid']
    list_display=["uuid", "name"]

admin.site.register(ChallengeCertificate)
admin.site.register(PropFirmChallenge)
admin.site.register(Competition, CompetitionAdmin)
admin.site.register(CompetitionResult)
# Register your models here.
