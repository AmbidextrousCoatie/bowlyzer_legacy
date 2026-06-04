# Copy to deploy.config.ps1 (gitignored) and adjust.
@{
    RemoteHost = "212.227.57.223"
    # Dedicated deploy user (see deploy/vps/setup-bowlyzer-user.sh). Use root only for one-time setup.
    RemoteUser = "bowlyzer"
    RemoteDir  = "/home/bowlyzer/bowlyzer"
    ReleaseImage = "bowlyzer:release"
    # ZipContainerImage = $true   # optional: gzip image tar before scp (default in deploy.ps1: $false)
}
