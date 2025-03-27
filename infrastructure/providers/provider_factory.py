from typing import List
import logging

from application.interfaces import StatusProvider
from infrastructure.providers.stripe_provider import StripeProvider
from infrastructure.providers.auth0_provider import Auth0StatusProvider
from infrastructure.providers.okta_provider import OktaStatusProvider
from infrastructure.providers.aws_provider import AWSStatusProvider

logger = logging.getLogger(__name__)

def create_all_providers() -> List[StatusProvider]:
    """
    Create instances of all available status providers.
    
    Returns:
        List[StatusProvider]: All initialized providers
    """
    providers = []
    
    # Initialize payment providers
    try:
        providers.append(StripeProvider())
        # TODO: Add Square and PayPal providers
    except Exception as e:
        logger.error(f"Failed to initialize payment providers: {str(e)}")
    
    # Initialize authentication providers
    try:
        providers.append(Auth0StatusProvider())
        # TODO: Add Firebase provide
    except Exception as e:
        logger.error(f"Failed to initialize authentication providers: {str(e)}")
    

    try:
        # Add Okta provider
        providers.append(OktaStatusProvider())
        
        # Add Auth0Provider when implemented
        # providers.append(Auth0Provider())
        
        # TODO: Add Firebase provider
    except Exception as e:
        logger.error(f"Failed to initialize authentication providers: {str(e)}")

    # Initialize cloud providers
    try:
        providers.append(AWSStatusProvider())
        # TODO: Add GCP and Azure providers
    except Exception as e:
        logger.error(f"Failed to initialize cloud providers: {str(e)}")
    
    return providers