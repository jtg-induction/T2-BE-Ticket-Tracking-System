from django.contrib import admin
from safedelete.admin import SafeDeleteAdmin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(SafeDeleteAdmin):
    list_display = (
        'email', 
        'first_name', 
        'last_name', 
        'role', 
        'is_deleted_status',
        'deleted'
    )
    
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-created_at',)

    def is_deleted_status(self, obj):
        """
        Returns a boolean icon: True if deleted, False otherwise.
        """
        return obj.deleted is not None
    
    is_deleted_status.boolean = True
    is_deleted_status.short_description = "Is Deleted?"
