"""
Escrow URL Configuration

This module defines URL patterns for the escrow app, including:
- Payment webhook endpoints
- Transaction management API endpoints
- Status and dispute handling endpoints

All API endpoints use UUID path converters for transaction IDs
to ensure proper validation and security.
"""

from django.urls import path
from . import views

# Define the app namespace for URL reversing
app_name = 'escrow'

urlpatterns = [
    # Payment webhook endpoint (no authentication required)
    # This endpoint receives notifications from Coinbase Commerce
    path('webhooks/coinbase/', views.coinbase_webhook, name='coinbase_webhook'),
    
    # Transaction management API endpoints (authentication required)
    path('api/transactions/', views.create_transaction, name='create_transaction'),
    path('api/transactions/<uuid:transaction_id>/', views.transaction_status, name='transaction_status'),
    path('api/transactions/<uuid:transaction_id>/dispute/', views.dispute_transaction, name='dispute_transaction'),
    
    # User-specific endpoints (authentication required)
    path('api/user/transactions/', views.user_transactions, name='user_transactions'),
]
