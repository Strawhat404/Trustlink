"""
Escrow Views

This module contains Django views for handling escrow-related HTTP requests.
Includes webhook endpoints for payment processing and API endpoints for
transaction management.

Key Features:
- Payment webhook handling for Coinbase Commerce
- Transaction status API endpoints
- Secure webhook signature verification
- Comprehensive error handling and logging
"""

import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .payment_service import PaymentService
from .services import EscrowService
from .models import EscrowTransaction

# Set up logging
logger = logging.getLogger('trustlink.escrow.views')

@csrf_exempt
@require_http_methods(["POST"])
def coinbase_webhook(request):
    """
    Handle Coinbase Commerce webhook notifications
    
    This endpoint receives payment notifications from Coinbase Commerce
    and processes them to update escrow transaction statuses.
    
    The webhook signature is verified to ensure authenticity.
    """
    
    try:
        # Get the signature from headers
        signature = request.META.get('HTTP_X_CC_WEBHOOK_SIGNATURE')
        if not signature:
            logger.warning("Webhook received without signature")
            return HttpResponse("Missing signature", status=400)
        
        # Get raw payload for signature verification
        payload = request.body
        
        # Verify webhook signature
        if not PaymentService.verify_webhook_signature(payload, signature):
            logger.warning("Invalid webhook signature")
            return HttpResponse("Invalid signature", status=401)
        
        # Parse webhook data
        try:
            webhook_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            return HttpResponse("Invalid JSON", status=400)
        
        # Process the webhook
        success = PaymentService.process_webhook(webhook_data)
        
        if success:
            logger.info("Webhook processed successfully")
            return HttpResponse("OK", status=200)
        else:
            logger.error("Failed to process webhook")
            return HttpResponse("Processing failed", status=500)
            
    except Exception as e:
        logger.error(f"Unexpected error in webhook handler: {str(e)}")
        return HttpResponse("Internal error", status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_status(request, transaction_id):
    """
    Get detailed status information for a transaction
    
    This endpoint returns comprehensive status information for an escrow
    transaction, including timeline, payment details, and recent activity.
    
    Args:
        transaction_id: UUID of the escrow transaction
        
    Returns:
        JSON response with transaction status information
    """
    
    try:
        # Get transaction status using service layer
        status_info = EscrowService.get_transaction_status(transaction_id)
        
        if status_info is None:
            return Response(
                {"error": "Transaction not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(status_info, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting transaction status: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_transactions(request):
    """
    Get transactions for the authenticated user
    
    This endpoint returns a list of transactions where the user is either
    the buyer or seller, with optional filtering by status.
    
    Query Parameters:
        status: Optional status filter (PENDING, FUNDED, etc.)
        limit: Maximum number of transactions to return (default: 10)
        
    Returns:
        JSON response with list of user transactions
    """
    
    try:
        # Get query parameters
        status_filter = request.GET.get('status')
        limit = int(request.GET.get('limit', 10))
        
        # Limit the maximum number of results
        limit = min(limit, 100)
        
        # TODO: Get TelegramUser from authenticated user
        # For now, this will need to be implemented when we add authentication
        # user_telegram = request.user.telegramuser
        
        # Placeholder response until authentication is implemented
        return Response({
            "message": "User transactions endpoint - authentication integration pending",
            "parameters": {
                "status_filter": status_filter,
                "limit": limit
            }
        }, status=status.HTTP_200_OK)
        
    except ValueError:
        return Response(
            {"error": "Invalid limit parameter"},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error getting user transactions: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_transaction(request):
    """
    Create a new escrow transaction
    
    This endpoint allows users to create new escrow transactions
    for purchasing Telegram groups.
    
    Request Body:
        seller_telegram_id: Telegram ID of the seller
        group_listing_id: UUID of the group listing
        amount: Payment amount
        currency: Currency code (USDT, ETH, BTC)
        
    Returns:
        JSON response with transaction details and payment URL
    """
    
    try:
        # TODO: Implement transaction creation
        # This will be fully implemented when we add the Telegram bot integration
        
        return Response({
            "message": "Transaction creation endpoint - full implementation pending",
            "data": request.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error creating transaction: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dispute_transaction(request, transaction_id):
    """
    Create a dispute for a transaction
    
    This endpoint allows buyers or sellers to open disputes
    when there are issues with the transaction.
    
    Request Body:
        description: Description of the dispute
        
    Returns:
        JSON response with dispute information
    """
    
    try:
        description = request.data.get('description')
        if not description:
            return Response(
                {"error": "Description is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # TODO: Get TelegramUser from authenticated user
        # TODO: Create dispute using EscrowService.create_dispute()
        
        return Response({
            "message": "Dispute creation endpoint - full implementation pending",
            "transaction_id": transaction_id,
            "description": description
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error creating dispute: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
