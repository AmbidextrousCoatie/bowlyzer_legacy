# Copy to deploy.config.ps1 (gitignored) and adjust.
@{
    RemoteHost = "212.227.57.223"
    RemoteUser = "root"
    RemoteDir  = "/root/bowlyzer"
    # Image tag used in docker-compose.prod.yml
    ReleaseImage = "bowlyzer:release"
}
