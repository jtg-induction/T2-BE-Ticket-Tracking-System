from django.contrib import admin
from django.contrib.auth import get_user_model

class UserAdmin(admin.ModelAdmin):
    list_display = ("email","first_name","last_name","is_staff","is_active","is_superuser")


admin.site.register(get_user_model(),UserAdmin)
