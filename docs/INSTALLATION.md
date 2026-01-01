# Installation Guide - Code Analysis Server

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

This guide describes how to install `code-analysis-server` as a systemd service on Ubuntu/Debian systems following standard Linux filesystem hierarchy.

## System Requirements

- Ubuntu 20.04+ or Debian 11+
- Python 3.8 or higher
- Root/sudo access
- Network access (for downloading dependencies)

## Directory Structure

After installation, the following directory structure will be created:

```
/etc/code-analysis-server/          # Configuration files
  └── config.json                   # Main configuration file
  └── mtls_certificates/            # SSL certificates (if used)

/usr/lib/code-analysis-server/      # Application files
  └── .venv/                        # Python virtual environment
  └── code_analysis/                # Application code
  └── ...

/var/lib/code-analysis-server/      # Data files (databases, indexes)
  └── code_analysis.db              # SQLite database
  └── faiss_index.bin               # FAISS vector index
  └── versions/                     # File version history
  └── dynamic_watch_dirs.json       # Dynamic watch directories

/var/log/code-analysis-server/      # Log files
  └── code_analysis.log             # Main server log
  └── vectorization_worker.log      # Vectorization worker log
  └── file_watcher.log              # File watcher log
  └── db_worker.log                 # Database worker log

/var/run/code-analysis-server/      # Runtime files (PID files, sockets)
```

## Installation Steps

### 1. Prerequisites

Ensure you have the required system packages:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip rsync
```

### 2. Run Installation Script

From the project root directory:

```bash
sudo ./scripts/install.sh
```

The installation script will:

1. **Create system user**: Creates a dedicated `code-analysis` system user
2. **Create directories**: Sets up all required directories with proper permissions
3. **Install package**: Copies application files to `/usr/lib/code-analysis-server/`
4. **Create virtual environment**: Sets up Python virtual environment and installs dependencies
5. **Install configuration**: Creates configuration file in `/etc/code-analysis-server/config.json`
6. **Install systemd service**: Installs and configures systemd service unit

### 3. Configure the Service

Edit the configuration file:

```bash
sudo nano /etc/code-analysis-server/config.json
```

Key configuration sections to review:

#### Database Path (already configured)
```json
{
  "code_analysis": {
    "db_path": "/var/lib/code-analysis-server/code_analysis.db",
    "faiss_index_path": "/var/lib/code-analysis-server/faiss_index.bin"
  }
}
```

#### Watch Directories
Configure which directories to monitor:

```json
{
  "code_analysis": {
    "worker": {
      "watch_dirs": [
        "/path/to/your/project1",
        "/path/to/your/project2"
      ]
    }
  }
}
```

#### SSL Certificates (if using mTLS)

If using mTLS, copy your certificates:

```bash
sudo mkdir -p /etc/code-analysis-server/mtls_certificates
sudo cp -r /path/to/your/certificates/* /etc/code-analysis-server/mtls_certificates/
sudo chown -R root:root /etc/code-analysis-server/mtls_certificates
sudo chmod -R 644 /etc/code-analysis-server/mtls_certificates
```

Then update paths in `config.json` to point to `/etc/code-analysis-server/mtls_certificates/...`

### 4. Start the Service

```bash
# Start the service
sudo systemctl start code-analysis-server

# Enable auto-start on boot
sudo systemctl enable code-analysis-server

# Check status
sudo systemctl status code-analysis-server
```

### 5. Verify Installation

Check service status:

```bash
sudo systemctl status code-analysis-server
```

View logs:

```bash
# Main server log
sudo tail -f /var/log/code-analysis-server/code_analysis.log

# Vectorization worker log
sudo tail -f /var/log/code-analysis-server/vectorization_worker.log

# File watcher log
sudo tail -f /var/log/code-analysis-server/file_watcher.log

# All logs via journald
sudo journalctl -u code-analysis-server -f
```

## Service Management

### Start/Stop/Restart

```bash
sudo systemctl start code-analysis-server
sudo systemctl stop code-analysis-server
sudo systemctl restart code-analysis-server
```

### Enable/Disable Auto-start

```bash
sudo systemctl enable code-analysis-server    # Enable auto-start
sudo systemctl disable code-analysis-server   # Disable auto-start
```

### View Logs

```bash
# Via journald (recommended)
sudo journalctl -u code-analysis-server -f

# Direct log files
sudo tail -f /var/log/code-analysis-server/*.log
```

### Reload Configuration

After changing configuration, restart the service:

```bash
sudo systemctl restart code-analysis-server
```

## Uninstallation

To remove the service:

```bash
sudo ./scripts/uninstall.sh
```

The uninstallation script will:

1. Stop and disable the service
2. Remove systemd service file
3. Ask for confirmation before removing:
   - Installation directory
   - Configuration directory
   - Data directory
   - Log directory
   - System user

## Troubleshooting

### Service fails to start

1. Check service status:
   ```bash
   sudo systemctl status code-analysis-server
   ```

2. Check logs:
   ```bash
   sudo journalctl -u code-analysis-server -n 50
   ```

3. Verify configuration:
   ```bash
   sudo python3 -m code_analysis.main --config /etc/code-analysis-server/config.json
   ```
   (Run without `--daemon` to see errors)

### Permission errors

Ensure directories have correct ownership:

```bash
sudo chown -R code-analysis:code-analysis /var/lib/code-analysis-server
sudo chown -R code-analysis:code-analysis /var/log/code-analysis-server
sudo chown -R code-analysis:code-analysis /var/run/code-analysis-server
```

### Database errors

Check database file permissions:

```bash
ls -la /var/lib/code-analysis-server/
sudo chown code-analysis:code-analysis /var/lib/code-analysis-server/*.db
```

### Port already in use

If the configured port is already in use, update `config.json`:

```json
{
  "server": {
    "port": 15001
  },
  "code_analysis": {
    "port": 15001
  }
}
```

## Security Considerations

1. **File Permissions**: The service runs as a dedicated system user (`code-analysis`) with minimal privileges
2. **Directory Access**: The service only has write access to:
   - `/var/lib/code-analysis-server/` (data)
   - `/var/log/code-analysis-server/` (logs)
   - `/var/run/code-analysis-server/` (runtime)
3. **Configuration**: Configuration files are owned by root and readable by the service user
4. **SSL Certificates**: Store certificates securely in `/etc/code-analysis-server/` with appropriate permissions

## Backup and Migration

### Backup

To backup the service:

```bash
# Backup configuration
sudo tar -czf code-analysis-config-backup.tar.gz /etc/code-analysis-server/

# Backup data
sudo tar -czf code-analysis-data-backup.tar.gz /var/lib/code-analysis-server/
```

### Migration

To migrate to another server:

1. Install the service on the new server
2. Copy configuration: `/etc/code-analysis-server/config.json`
3. Copy data: `/var/lib/code-analysis-server/`
4. Copy SSL certificates if used
5. Update configuration paths if needed
6. Restart the service

## Support

For issues or questions:
- Email: vasilyvz@gmail.com
- Check logs: `/var/log/code-analysis-server/`
- System logs: `sudo journalctl -u code-analysis-server`

