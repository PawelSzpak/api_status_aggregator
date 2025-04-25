from domain import ProviderConfiguration
from infrastructure.providers.auth0_provider import Auth0StatusProvider

def configure_auth0_provider():
    """Configure and initialize the Auth0StatusProvider.
    
    Returns:
        Configured Auth0StatusProvider instance
    """
    # Create provider configuration
    config = ProviderConfiguration(
        name="Auth0",
        category="auth",
        status_url="https://status.auth0.com",
        rate_limit=5,
        check_interval=300,  # Check every 5 minutes
        # Additional provider-specific configuration can be added here
    )
    
    # Initialize provider with configuration
    return Auth0StatusProvider(config)

def example_usage():
    """Example usage of the Auth0StatusProvider."""
    provider = configure_auth0_provider()
    
    try:
        # Get current status
        status = provider.get_status()
        print(f"Auth0 Status: {status.status.name}")
        print(f"Status Message: {status.message}")
        print(f"Last Updated: {status.last_updated}")
        
        # Get active incidents
        incidents = provider.fetch_active_incidents()
        print(f"\nActive Incidents: {len(incidents)}")
        
        for i, incident in enumerate(incidents, 1):
            print(f"\nIncident {i}:")
            print(f"  Title: {incident.title}")
            print(f"  Status: {incident.status}")
            print(f"  Impact: {incident.impact}")
            print(f"  Region: {incident.region}")
            print(f"  Affected Components: {', '.join(incident.affected_components)}")
            print(f"  Latest Update: {incident.message}")
    
    except ConnectionError as e:
        print(f"Connection Error: {e}")
    except ValueError as e:
        print(f"Parsing Error: {e}")

if __name__ == "__main__":
    example_usage()