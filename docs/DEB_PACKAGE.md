# Building Debian Package

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Prerequisites

Install required build tools:

```bash
sudo apt-get update
sudo apt-get install -y devscripts debhelper dh-python python3-all python3-setuptools python3-pip python3-venv
```

## Building the Package

### Quick Build

From the project root directory:

```bash
./scripts/build_deb.sh
```

This will:
1. Clean previous builds
2. Build the Debian package
3. Create `.deb` file in the parent directory

### Manual Build

```bash
# Clean previous builds
rm -rf debian/code-analysis-server debian/files
rm -rf ../code-analysis-server_*.deb ../code-analysis-server_*.dsc ../code-analysis-server_*.tar.gz

# Build package
dpkg-buildpackage -us -uc -b
```

The `.deb` file will be created in the parent directory.

## Installing the Package

### Install from .deb file

```bash
# Install package
sudo dpkg -i ../code-analysis-server_*.deb

# If there are dependency issues, fix them:
sudo apt-get install -f
sudo dpkg -i ../code-analysis-server_*.deb
```

### After Installation

1. **Review configuration**:
   ```bash
   sudo nano /etc/code-analysis-server/config.json
   ```

2. **Configure watch directories** in the config file

3. **Copy SSL certificates** if using mTLS:
   ```bash
   sudo mkdir -p /etc/code-analysis-server/mtls_certificates
   sudo cp -r /path/to/certificates/* /etc/code-analysis-server/mtls_certificates/
   ```

4. **Start and enable service**:
   ```bash
   sudo systemctl start code-analysis-server
   sudo systemctl enable code-analysis-server
   ```

## Package Structure

The Debian package installs:

- **Application**: `/usr/lib/code-analysis-server/`
- **Configuration**: `/etc/code-analysis-server/`
- **Data**: `/var/lib/code-analysis-server/` (databases, indexes)
- **Logs**: `/var/log/code-analysis-server/`
- **Systemd service**: `/lib/systemd/system/code-analysis-server.service`
- **Documentation**: `/usr/share/doc/code-analysis-server/`

## Package Contents

The package includes:

- Python package (`code_analysis`)
- Systemd service file
- Configuration template
- Installation scripts (preinst, postinst, prerm, postrm)
- Documentation

## Uninstalling

```bash
sudo apt-get remove code-analysis-server
# or
sudo dpkg -r code-analysis-server
```

To also remove configuration and data:

```bash
sudo apt-get purge code-analysis-server
# or
sudo dpkg -P code-analysis-server
```

## Troubleshooting

### Build Errors

If you get errors about missing dependencies:

```bash
sudo apt-get build-dep code-analysis-server
```

### Installation Errors

If installation fails due to missing dependencies:

```bash
sudo apt-get install -f
```

### Service Issues

Check service status:

```bash
sudo systemctl status code-analysis-server
sudo journalctl -u code-analysis-server -f
```

## Package Version

Update version in:

1. `debian/changelog` - Update version and changelog
2. `setup.py` - Update version
3. `pyproject.toml` - Update version

Then rebuild the package.

## Signing Packages (Optional)

To sign packages for distribution:

```bash
dpkg-buildpackage -k<GPG_KEY_ID> -us -uc
```

## Distribution

The built `.deb` file can be:

1. Installed directly on Ubuntu/Debian systems
2. Added to a local APT repository
3. Distributed via package hosting services

