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

## Command Inventory Utility

**`command_inventory.py`** - Comprehensive command discovery and verification tool.

This utility provides multiple modes:
- **discover**: Find all commands from registry and update documentation
- **check**: Verify command files, imports, and registration
- **verify**: Check command availability via MCP interface
- **full**: Run all checks (default)

### Usage

```bash
# Run full inventory (discover + check + verify)
python scripts/command_inventory.py

# Only discover commands and update documentation
python scripts/command_inventory.py --mode discover

# Only check command registration
python scripts/command_inventory.py --mode check

# Only verify via MCP
python scripts/command_inventory.py --mode verify

# Custom output file
python scripts/command_inventory.py --mode discover --output custom_inventory.md

# Verbose output
python scripts/command_inventory.py --mode full --verbose
```

### Options

- `--mode {discover,check,verify,full}` - Operation mode (default: full)
- `--output OUTPUT` - Output file for discover mode (default: docs/COMMAND_INVENTORY.md)
- `--server-id SERVER_ID` - Server ID for verify mode (default: code-analysis-server)
- `-v, --verbose` - Verbose output

