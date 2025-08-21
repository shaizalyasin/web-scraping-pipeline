import yaml

# Load the configuration from YAML file
with open('config/sectors.yaml', 'r') as f:
    config = yaml.safe_load(f)

wine_config = config['europages_wine']
print("✅ Configuration loaded successfully!")
print(f"Target URL: {wine_config['search_url']}")
print(f"Max pages to scrape: {wine_config['max_pages']}")