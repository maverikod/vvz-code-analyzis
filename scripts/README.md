# Installation Scripts

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Quick Start

### Installation

```bash
sudo ./scripts/install.sh
```

### Uninstallation

```bash
sudo ./scripts/uninstall.sh
```

## Files

- `install.sh` - Installation script that sets up code-analysis-server as a systemd service
- `uninstall.sh` - Uninstallation script that removes the service
- `systemd/code-analysis-server.service` - Systemd unit file

## What Gets Installed

- **System user**: `code-analysis` (dedicated user for the service)
- **Configuration**: `/etc/code-analysis-server/config.json`
- **Application**: `/usr/lib/code-analysis-server/`
- **Data**: `/var/lib/code-analysis-server/` (databases, indexes)
- **Logs**: `/var/log/code-analysis-server/`
- **Systemd service**: `code-analysis-server.service`

## After Installation

1. Review configuration: `sudo nano /etc/code-analysis-server/config.json`
2. Configure watch directories in the config file
3. Copy SSL certificates if using mTLS: `/etc/code-analysis-server/mtls_certificates/`
4. Start service: `sudo systemctl start code-analysis-server`
5. Enable auto-start: `sudo systemctl enable code-analysis-server`

## Service Management

```bash
# Start/Stop/Restart
sudo systemctl start code-analysis-server
sudo systemctl stop code-analysis-server
sudo systemctl restart code-analysis-server

# Status and logs
sudo systemctl status code-analysis-server
sudo journalctl -u code-analysis-server -f
```

For detailed documentation, see [docs/INSTALLATION.md](../docs/INSTALLATION.md).

