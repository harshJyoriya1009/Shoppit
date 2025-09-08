from django.shortcuts import render
from rest_framework.decorators import api_view , permission_classes
from .models import Product, Cart, CartItem, Transaction
from .serializers import ProductSerializer, DetailedProductSerializer, CartItemSerializer, UserSerializer, SimpleCartSerializer, CartSerializer
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from decimal import Decimal
import uuid
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken 

BASE_URL = settings.REACT_BASE_URL
# Create your views here.

@api_view(["GET"])
def products(request):
    products = Product.objects.all()
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def product_detail(request,slug):
    product = Product.objects.get(slug=slug)
    serializer = DetailedProductSerializer(product)
    return Response(serializer.data) 

@api_view(["POST"])
# def add_item(request):
#     try:
#         cart_code = request.data.get("cart_code")
#         product_id = request.data.get("product_id")

#         cart, created = Cart.objects.get_or_create(cart_code=cart_code)
#         product = Product.objects.get(id=product_id)

#         cartitem,created = CartItem.objects.get_or_create(cart=cart,product=product)
#         cartitem.quantity=1
#         cartitem.save()

#         serializer = CartItemSerializer(cartitem)
#         return Response({"data":serializer.data, "message":"Cartitem created successfully"}, status=201)

#     except Exception as e:
#         return Response({"error":str(e)}, status=400)

def add_item(request):
    try:
        product_id = request.data.get("product_id")
        user = request.user if request.user.is_authenticated else None

        # If user is logged in, get or create cart for them
        if user:
            cart, created = Cart.objects.get_or_create(user=user, paid=False)
        else:
            cart_code = request.data.get("cart_code")
            cart, created = Cart.objects.get_or_create(cart_code=cart_code, paid=False)

        product = Product.objects.get(id=product_id)

        cartitem, created = CartItem.objects.get_or_create(cart=cart, product=product)
        cartitem.quantity = 1
        cartitem.save()

        serializer = CartItemSerializer(cartitem)
        return Response({"data": serializer.data, "message": "Cartitem created successfully"}, status=201)

    except Exception as e:
        return Response({"error": str(e)}, status=400)

    

@api_view(["GET"])
def product_in_cart(request):
    cart_code = request.query_params.get("cart_code")
    product_id = request.query_params.get("product_id")

    cart = Cart.objects.get(cart_code=cart_code)
    product = Product.objects.get(id=product_id)

    product_exists_in_cart = CartItem.objects.filter(cart=cart,product=product).exists()

    return Response({'product_in_cart': product_exists_in_cart})


@api_view(["GET"])
# def get_cart_stat(request):
#     cart_code = request.query_params.get("cart_code")
#     cart = Cart.objects.get(cart_code=cart_code, paid=False)
#     serializer = SimpleCartSerializer(cart)
#     return Response(serializer.data)

def get_cart_stat(request):
    user = request.user if request.user.is_authenticated else None
    if user:
        cart, created = Cart.objects.get_or_create(user=user, paid=False)
    else:
        cart_code = request.query_params.get("cart_code")
        cart, created = Cart.objects.get_or_create(cart_code=cart_code, paid=False)
    serializer = SimpleCartSerializer(cart)
    return Response(serializer.data)


@api_view(["GET"])
def get_cart(request):
    cart_code = request.query_params.get("cart_code")
    cart = Cart.objects.get(cart_code=cart_code,paid=False)
    serializer = CartSerializer(cart)
    return Response(serializer.data)


@api_view(["PATCH"])
def update_quantity(request):
    try:
        cartitem_id = request.data.get("item_id")
        quantity = request.data.get("quantity")
        quantity = int(quantity)
        cartitem = CartItem.objects.get(id = cartitem_id)
        cartitem.quantity = quantity
        cartitem.save()
        serializer = CartItemSerializer(cartitem)
        return Response({"data":serializer.data, "message": "Cartitem updated...."})

    except Exception as e:
        return Response({"error": str(e)}, status=400)
    

# @api_view(["POST"])
# def delete_cartitem(request):
#     cartitem_id = request.data.get("item_id")
#     cartitem = CartItem.objects.get(id=cartitem_id)
#     cartitem.delete()
#     return Response({"message": "Item deleted successfully"},status=status.HTTP_204_NO_CONTENT)

@api_view(["POST"])
def delete_cartitem(request):
    cartitem_id = request.data.get("item_id")
    try:
        cartitem = CartItem.objects.get(id=cartitem_id)
        cartitem.delete()
        return Response({"message": "Item deleted successfully"}, status=status.HTTP_200_OK)
    except CartItem.DoesNotExist:
        return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)
    

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_username(request):
    user = request.user
    return Response({"username": user.username})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_info(request):
    user = request.user
    serializer = UserSerializer(user)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    if request.user:
        try:
            tx_ref = str(uuid.uuid4())
            cart_code = request.data.get("cart_code")
            cart = Cart.objects.get(cart_code=cart_code)
            user = request.user

            # amount = sum([item.quantity * item.product.price for item in cart.item.all()])
            amount = sum([item.quantity * item.product.price for item in cart.items.all()])

            total_amount = amount
            currency = "INR"
            redirect_url = f"{BASE_URL}/payment-status/"

            transaction = Transaction.objects.create(
                ref = tx_ref,
                cart=cart,
                amount = total_amount,
                currency = currency,
                user = user,
                status = "pending"
            )

            flutterwave_payload = {
                "tx_ref" : tx_ref,
                "amount" : str(total_amount),
                "currency" : currency,
                "redirect_url" : redirect_url,
                "customer" : {
                    "email": user.email,
                    "name": user.username,
                },
                "customizations": {
                    "title": "Jyoriya_Store Payment"
                }
            }

            # Set up header for the request
            headers = {
                "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                "content-type": "application/json"
            }

            # Make the API request to flutterwave
            response = requests.post(
                'https://api.flutterwave.com/v3/payments',
                json = flutterwave_payload,
                headers = headers
            )

            # Check if the request was successfull
            if response.status_code == 200:
                return Response(response.json(), status=status.HTTP_200_OK)

            else:
                return Response(response.json(), status=response.status_code)
            

        except requests.exceptions.RequestException as e:
            return Response({"error": str(e)} , status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# @api_view(["POST"])
# def payment_callback(request):
#     status = request.GET.get('status')
#     tx_ref = request.GET.get('tx_ref')
#     transaction_id = request.GET.get("transaction_id")

#     user = request.user

#     if status == 'successful':
#         headers ={
#             "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"
#         }

#         response = requests.get(f"https://api.flutterwave.com/v3/transaction/{transaction_id}/verify", headers=headers)
#         response_data = response.json()

#         if response_data['status'] == 'success':
#             transaction = Transaction.objects.get(ref = tx_ref)

#             if(response_data['data']['status'] == 'successful'
#                     and float(response_data['data']['amount']) == float(transaction.amount)
#                     and response_data['data']['currency'] == transaction.currency):
                
#                 transaction.status == 'completed'
#                 transaction.save()

#                 cart = transaction.cart
#                 cart.paid = True
#                 cart.user = user
#                 cart.save()

#                 return Response({'message': 'Payment Successful', 'submessage': 'you have successfully made your payment'})
            
#             else:
#                 return Response({'message': 'Payment verification failed', 'submessage': 'your payment verification failed'})
            
#         else:
#             return Response({'message': 'failed to verify transaction through flutterwave', 'submessage': 'we could not take your transaction'})
        
#     else:
#         return Response({'message': 'Payment was not successfull'}, status=400)


@api_view(["POST"])
def payment_callback(request):
    status_param = request.GET.get('status')
    tx_ref = request.GET.get('tx_ref')
    transaction_id = request.GET.get("transaction_id")

    if not transaction_id:
        return Response({"error": "Missing transaction_id"}, status=400)

    user = request.user if request.user.is_authenticated else None

    if status_param == 'successful':
        headers = {
            "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"
        }

        url = f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify"
        response = requests.get(url, headers=headers)

        try:
            response_data = response.json()
        except Exception:
            return Response(
                {"error": "Invalid response from Flutterwave", "raw": response.text},
                status=500
            )

        if response_data['status'] == 'success':
            transaction = Transaction.objects.get(ref=tx_ref)

            if (
                response_data['data']['status'] == 'successful'
                and float(response_data['data']['amount']) == float(transaction.amount)
                and response_data['data']['currency'] == transaction.currency
            ):
                transaction.status = 'completed'
                transaction.save()

                cart = transaction.cart
                cart.paid = True
                if user:
                    cart.user = user
                cart.save()

                return Response({
                    'message': 'Payment Successful',
                    'subMessage': 'You have successfully made your payment'
                })

            else:
                return Response({
                    'message': 'Payment verification failed',
                    'subMessage': 'Your payment verification failed'
                })

        return Response({
            'message': 'Failed to verify transaction through Flutterwave',
            'subMessage': 'We could not verify your transaction'
        })

    return Response({'message': 'Payment was not successful'}, status=400)


User = get_user_model()  # <-- now it points to core.CustomUser

# @api_view(["POST"])
# def register_user(request):
#     try:
#         username = request.data.get("username")
#         email = request.data.get("email")
#         password = request.data.get("password")
#         address = request.data.get("address")
#         city = request.data.get("city")
#         state = request.data.get("state")

#         if not username or not password:
#             return Response({"error": "Username and password required"}, status=status.HTTP_400_BAD_REQUEST)

#         if User.objects.filter(username=username).exists():
#             return Response({"error": "Username already exists"}, status=status.HTTP_400_BAD_REQUEST)

#         # ✅ create user with your CustomUser model
#         user = User.objects.create_user(
#             username=username,
#             email=email,
#             password=password,
#             address=address,
#             city=city,
#             state=state
#         )

#          cart = Cart.objects.create(
#             cart_code=str(uuid.uuid4()),
#             user=user,
#             paid=False
#         )

#         # ✅ generate JWT tokens
#         refresh = RefreshToken.for_user(user)

#         return Response(
#             {
#                 "message": "Account created successfully!",
#                 "user": UserSerializer(user).data,
#                 "cart_code": cart.cart_code,
#                 "refresh": str(refresh),
#                 "access": str(refresh.access_token),
#             },
#             status=status.HTTP_201_CREATED,
#         )

#     except Exception as e:
#         return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def register_user(request):
    try:
        username = request.data.get("username")
        email = request.data.get("email")
        password = request.data.get("password")
        address = request.data.get("address")
        city = request.data.get("city")
        state = request.data.get("state")

        if not username or not password:
            return Response(
                {"error": "Username and password required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "Username already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create the user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            address=address,
            city=city,
            state=state
        )

        # Create a new cart for this user
        cart = Cart.objects.create(
            cart_code=str(uuid.uuid4()),
            user=user,
            paid=False
        )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Account created successfully!",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "address": user.address,
                    "city": user.city,
                    "state": user.state,
                },
                "cart_code": cart.cart_code,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            status=status.HTTP_201_CREATED
        )

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)