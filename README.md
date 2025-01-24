# AWS Log Searcher

A GUI tool for searching and filtering AWS CloudWatch logs with ease.

## Installation

1. Clone the project:
```bash
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
brew install python-tk
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

### Multi-tab Support
- Open multiple search tabs simultaneously
- Each tab maintains its own search context and history
- Keyboard shortcuts:
  - New Tab: `⌘T` (macOS) / `Ctrl+T` (Windows/Linux)
  - Close Tab: `⌘⌫` (macOS) / `Ctrl+Backspace` (Windows/Linux)

### Search Capabilities
- Real-time AWS CloudWatch log searching
- Quick search within logs: `⌘F` (macOS) / `Ctrl+F` (Windows/Linux)
- Search selected text in new tab: `⌘D` (macOS) / `Ctrl+D` (Windows/Linux)
- Right-click context menu for quick search options

### Filtering & Organization
- Real-time log filtering with debounced input
- Path-based filtering with dropdown selection
- Environment selection (QA/SB/PROD)
- Time-based search range configuration
- Automatic time-based log sorting

### Visual Features
- Color-coded log levels:
  - INFO: Green
  - WARN: Orange
  - ERROR: Red
- Timestamp highlighting in cyan
- Search term highlighting in red
- Dark theme optimized for long sessions

### User Interface
- Clean and intuitive interface
- Progress indicators for active searches
- Status updates for search operations
- Resizable window with proper layout management
- Customizable through preferences menu

### Additional Features
- Stop/Resume search operations
- Clear log content
- Copy log content
- Configurable through `config.json`
- Persistent settings between sessions