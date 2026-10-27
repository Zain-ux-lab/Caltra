"""Keep an existing private key file outside cloud-synced project folders."""
def env_file(project,home):
    local=home/'.config/caltra/.env'
    existing=project/'.env'
    return local if not existing.exists() and local.exists() else existing
