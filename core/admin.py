from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Event, EventMembership, Transaction, TransactionSplit


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('App Role', {'fields': ('is_admin',)}),
    )


class EventMembershipInline(admin.TabularInline):
    model = EventMembership
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    inlines = [EventMembershipInline]


class TransactionSplitInline(admin.TabularInline):
    model = TransactionSplit
    extra = 0


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    inlines = [TransactionSplitInline]


@admin.register(EventMembership)
class EventMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'event', 'balance']
