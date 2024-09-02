# LevelUp API Service

This repository contains the code for the `LevelUp API`, a companion API for a leveling cog for the `Red-DiscordBot`. This guide will help you clone the repository and set up your own self-hosted API.

## Prerequisites

- Python 3.10 or higher
- pip (Python package installer)
- Virtual environment (`venv`)
- git
- systemd (for setting up the service)

## Installation and Setup

### 1. Create a Virtual Environment

It's best practice to use a virtual environment to manage dependencies:

```bash
python3 -m venv apienv
```

### 2. Activate the Virtual Environment

Before installing the required packages, activate the virtual environment:

```bash
source apienv/bin/activate
```

### 3. Clone the Repository

```bash
git clone https://github.com/vertyco/vrt-cogs.git
cd vrt-cogs/levelup/generator
```

### 4. Install Dependencies

Install the required Python packages using `pip`:

```bash
pip install -r requirements.txt
```

### 5. Test the API

Before setting up the service, you can test the API to ensure it's working:

```bash
cd /home/ubuntu/vrt-cogs/levelup/generator
```

```bash
uvicorn api:app --host 0.0.0.0 --port 8888 --app-dir /home/ubuntu/vrt-cogs/levelup/generator
```

### 6. Set Up the systemd Service

Create a new systemd service file for the API:

```bash
sudo nano /etc/systemd/system/levelup.service
```

Add the following content to the file:

```ini
[Unit]
Description=LevelUp API Service
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/home/ubuntu/redenv/bin/uvicorn api:app --host 0.0.0.0 --port 8888 --workers 4 --app-dir /home/ubuntu/vrt-cogs/levelup/generator
User=ubuntu
Group=ubuntu
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```

### 7. Reload systemd Daemon

Reload the systemd configuration to apply the changes:

```bash
sudo systemctl daemon-reload
```

### 8. Start and Enable the Service

Start the service:

```bash
sudo systemctl start levelup.service
```

Enable the service to start on boot:

```bash
sudo systemctl enable levelup.service
```

### 9. Check the Service Status

You can check the status of the service to ensure it is running correctly:

```bash
sudo systemctl status levelup.service
```

### 10. View Logs

You can view the logs for the service using:

```bash
sudo journalctl -u levelup.service -f
```

## Troubleshooting

If you encounter any issues, please check the logs for more details:

```bash
sudo journalctl -u levelup.service -n 50 -f
```

## DISCLAIMER

By using this API it is assumed you know your way around Python and hosting services. This guide is not exhaustive and may require additional steps based on your environment. I will not be providing support for setting up the API on your server.
