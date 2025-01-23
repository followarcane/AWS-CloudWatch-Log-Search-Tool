# AWS Log Searcher

A GUI tool for searching and filtering AWS CloudWatch logs with ease.

## Installation

1. Clone the project:
```bash
git clone https://github.com/yourusername/aws-log-searcher.git
cd aws-log-searcher
```

2. Create and activate virtual environment:
```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python3 -m venv venv
.\venv\Scripts\activate
```

3. Install required packages:
```bash
pip3 install -r requirements.txt
```

4. Run the application:
```bash
python3 main.py
```

## Quick Access for iTerm2

Add the following alias to your `.zshrc` or `.bashrc` file for quick access in iTerm2:

```bash
alias logsearch="cd /path/to/aws-log-searcher && source venv/bin/activate && python3 main.py"
```

Now you can start the application by simply typing `logsearch` in your terminal.

## Features

- Multi-tab support
- Real-time log filtering
- Path-based filtering
- Quick search with right-click menu
- Keyboard shortcuts
- Time-based sorting
- Color-coded log levels