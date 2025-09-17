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
from django.shortcuts import render
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
from .models import EscrowTransaction, TelegramUser, DisputeCase, AuditLog

# Set up logging
logger = logging.getLogger('trustlink.escrow.views')

def escrow_index(request):
    """
    Escrow system status page
    
    This view provides an overview of the escrow system status,
    including statistics and available API endpoints.
    """
    
    try:
        # Get system statistics
        total_transactions = EscrowTransaction.objects.count()
        active_transactions = EscrowTransaction.objects.filter(
            status__in=['PENDING', 'FUNDED', 'AWAITING_TRANSFER', 'VERIFYING']
        ).count()
        completed_transactions = EscrowTransaction.objects.filter(status='COMPLETED').count()
        disputed_transactions = EscrowTransaction.objects.filter(status='DISPUTED').count()
        total_users = TelegramUser.objects.count()
        open_disputes = DisputeCase.objects.filter(status='OPEN').count()
        
        # Recent activity
        recent_transactions = EscrowTransaction.objects.select_related(
            'buyer', 'seller', 'group_listing'
        ).order_by('-created_at')[:5]
        
        context = {
            'stats': {
                'total_transactions': total_transactions,
                'active_transactions': active_transactions,
                'completed_transactions': completed_transactions,
                'disputed_transactions': disputed_transactions,
                'total_users': total_users,
                'open_disputes': open_disputes,
            },
            'recent_transactions': recent_transactions,
            'api_endpoints': [
                {'url': '/escrow/api/transactions/', 'method': 'POST', 'description': 'Create new transaction'},
                {'url': '/escrow/api/transactions/<id>/', 'method': 'GET', 'description': 'Get transaction status'},
                {'url': '/escrow/api/transactions/<id>/dispute/', 'method': 'POST', 'description': 'Create dispute'},
                {'url': '/escrow/api/user/transactions/', 'method': 'GET', 'description': 'Get user transactions'},
                {'url': '/escrow/webhooks/coinbase/', 'method': 'POST', 'description': 'Coinbase Commerce webhook'},
            ]
        }
        
        return render(request, 'escrow/index.html', context)
        
    except Exception as e:
        logger.error(f"Error in escrow index view: {str(e)}")
        return render(request, 'escrow/index.html', {
            'error': 'Unable to load system statistics'
        })

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
        # Map authenticated Django user to TelegramUser
        try:
            buyer = request.user.telegramuser  # OneToOne on TelegramUser.user
        except Exception:
            return Response({"error": "Authenticated user is not linked to a Telegram account"}, status=status.HTTP_401_UNAUTHORIZED)

        seller_telegram_id = request.data.get('seller_telegram_id')
        group_listing_id = request.data.get('group_listing_id')
        amount = request.data.get('amount')
        currency = request.data.get('currency')

        # Validate inputs
        if not all([seller_telegram_id, group_listing_id, amount, currency]):
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

        from decimal import Decimal
        from groups.models import GroupListing

        try:
            amount_dec = Decimal(str(amount))
        except Exception:
            return Response({"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            seller = TelegramUser.objects.get(telegram_id=seller_telegram_id)
        except TelegramUser.DoesNotExist:
            return Response({"error": "Seller not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            group_listing = GroupListing.objects.get(id=group_listing_id, seller=seller, status='ACTIVE')
        except GroupListing.DoesNotExist:
            return Response({"error": "Active group listing not found for seller"}, status=status.HTTP_404_NOT_FOUND)

        # Create escrow transaction
        txn = EscrowService.create_transaction(
            buyer=buyer,
            seller=seller,
            group_listing=group_listing,
            amount=amount_dec,
            currency=currency,
            usd_equivalent=group_listing.price_usd
        )

        # Create payment charge
        ok, charge = PaymentService.create_payment_charge(
            transaction=txn,
            redirect_url=request.build_absolute_uri(f"/escrow/api/transactions/{txn.id}/"),
            cancel_url=request.build_absolute_uri("/escrow/")
        )

        if not ok:
            return Response({"error": "Failed to create payment charge", "details": charge.get('error')}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({
            "transaction_id": str(txn.id),
            "status": txn.status,
            "amount": str(txn.amount),
            "currency": txn.currency,
            "payment_url": charge.get("payment_url"),
            "charge_id": charge.get("charge_id")
        }, status=status.HTTP_201_CREATED)

    except ValueError as ve:
        return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
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
            return Response({"error": "Description is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Map authenticated user
        try:
            opened_by = request.user.telegramuser
        except Exception:
            return Response({"error": "Authenticated user is not linked to a Telegram account"}, status=status.HTTP_401_UNAUTHORIZED)

        # Create dispute
        dispute = EscrowService.create_dispute(
            transaction_id=transaction_id,
            opened_by=opened_by,
            description=description
        )

        if not dispute:
            return Response({"error": "Failed to create dispute"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "dispute_id": dispute.id,
            "status": dispute.status,
            "opened_by": opened_by.username or str(opened_by.telegram_id),
            "created_at": dispute.created_at.isoformat()
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"Error creating dispute: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
