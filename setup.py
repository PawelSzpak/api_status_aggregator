from setuptools import setup, find_packages

setup(
    name="api_status_aggregator",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "flask>=2.0.0",
        "beautifulsoup4>=4.9.0",
        "requests>=2.25.0",
        "sqlalchemy>=1.4.0",
        "psycopg2-binary>=2.9.0",
        "apscheduler>=3.8.0",
    ]
)
