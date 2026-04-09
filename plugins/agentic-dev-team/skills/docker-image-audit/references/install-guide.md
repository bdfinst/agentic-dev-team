# Docker Audit Tool Installation Guide

When the user is missing hadolint, trivy, or grype, share the relevant section below.

## hadolint

Hadolint is a Dockerfile linter that also integrates ShellCheck for `RUN` instructions.

- **macOS**: `brew install hadolint`
- **Windows** (Scoop): `scoop install hadolint`
- **Linux** (binary):
  ```bash
  curl -sL -o /usr/local/bin/hadolint \
    "https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64"
  chmod +x /usr/local/bin/hadolint
  ```
- **Docker** (no install): `docker run --rm -i hadolint/hadolint < Dockerfile`
- **All platforms**: Download from [GitHub releases](https://github.com/hadolint/hadolint/releases)

## Trivy

Trivy scans container images, filesystems, and git repos for vulnerabilities, misconfigurations, and secrets.

- **macOS**: `brew install trivy`
- **Linux** (apt):
  ```bash
  sudo apt-get install -y wget apt-transport-https gnupg lsb-release
  wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor | sudo tee /usr/share/keyrings/trivy.gpg > /dev/null
  echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/trivy.list
  sudo apt-get update && sudo apt-get install -y trivy
  ```
- **Linux** (rpm):
  ```bash
  cat << 'EOF' | sudo tee /etc/yum.repos.d/trivy.repo
  [trivy]
  name=Trivy repository
  baseurl=https://aquasecurity.github.io/trivy-repo/rpm/releases/$basearch/
  gpgcheck=0
  enabled=1
  EOF
  sudo yum -y install trivy
  ```
- **Docker** (no install): `docker run --rm aquasec/trivy image <image-name>`
- **All platforms**: See [aquasecurity/trivy installation docs](https://aquasecurity.github.io/trivy/latest/getting-started/installation/)

## Grype

Grype scans container images and filesystems for known vulnerabilities using Anchore's database.

- **macOS**: `brew install grype`
- **Linux / macOS** (install script):
  ```bash
  curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin
  ```
- **Docker** (no install): `docker run --rm anchore/grype:latest <image-name>`
- **All platforms**: See [anchore/grype installation docs](https://github.com/anchore/grype#installation)

## Verify installation

```bash
command -v hadolint && command -v trivy && command -v grype
```

If all three are installed, this prints their paths.
