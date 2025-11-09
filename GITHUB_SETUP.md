# GitHub Repository Setup Instructions

## Prerequisites

1. GitHub account
2. Git installed on your machine
3. This project ready to push

## Steps to Push to GitHub

### 1. Initialize Git Repository (if not already done)

```bash
git init
```

### 2. Add All Files

```bash
git add .
```

### 3. Create Initial Commit

```bash
git commit -m "Initial commit: QueueCTL - Background Job Queue System"
```

### 4. Create GitHub Repository

1. Go to [GitHub](https://github.com)
2. Click the "+" icon in the top right
3. Select "New repository"
4. Name it: `queuectl` or `flam-assignment-queuectl`
5. Make it **Public**
6. **Do NOT** initialize with README, .gitignore, or license (we already have these)
7. Click "Create repository"

### 5. Add Remote and Push

```bash
# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/queuectl.git

# Push to GitHub
git branch -M main
git push -u origin main
```

## Recording the Demo Video

### Option 1: Using OBS Studio (Recommended)

1. Download [OBS Studio](https://obsproject.com/)
2. Install and open OBS
3. Add "Display Capture" source
4. Start recording
5. Demonstrate the following:
   - Installation: `pip install -r requirements.txt`
   - Enqueue jobs: `queuectl enqueue '{"id":"job1","command":"echo Hello World"}'`
   - Start workers: `queuectl worker start --count 2`
   - Check status: `queuectl status`
   - List jobs: `queuectl list`
   - Show failed job retry: Enqueue a failing job and show retries
   - Show DLQ: `queuectl dlq list`
   - Stop workers: `queuectl worker stop`
6. Stop recording
7. Export video (MP4 format)

### Option 2: Using Screen Recording on Mac

1. Press `Cmd + Shift + 5`
2. Select "Record Entire Screen" or "Record Selected Portion"
3. Click "Record"
4. Perform demo
5. Stop recording (saved to Desktop)

### Option 3: Using Windows Game Bar

1. Press `Win + G`
2. Click "Record" button
3. Perform demo
4. Stop recording (saved to Videos/Captures)

### Option 4: Using Simple Screen Recorder (Linux)

```bash
sudo apt install simplescreenrecorder
simplescreenrecorder
```

## Uploading to Google Drive

1. Go to [Google Drive](https://drive.google.com)
2. Click "New" → "File upload"
3. Select your demo video
4. Right-click the uploaded file → "Get link"
5. Change sharing to "Anyone with the link"
6. Copy the link
7. Update the link in `README.md`:
   - Replace `YOUR_VIDEO_ID` with the actual video ID from the Drive link
   - Or use the full shareable link

### Example Drive Link Format

```
https://drive.google.com/file/d/VIDEO_ID/view?usp=sharing
```

Update in README.md:
```markdown
**Working CLI Demo**: [Watch the demo video here](https://drive.google.com/file/d/VIDEO_ID/view?usp=sharing)
```

## Demo Script (What to Show)

### 1. Installation (30 seconds)
```bash
pip install -r requirements.txt
pip install -e .
```

### 2. Basic Job Execution (1 minute)
```bash
# Enqueue a job
queuectl enqueue '{"id":"demo1","command":"echo Hello from QueueCTL"}'

# Start a worker
queuectl worker start --count 1

# Wait a moment, then check status
queuectl status

# List completed jobs
queuectl list --state completed

# Stop worker
queuectl worker stop
```

### 3. Multiple Workers (1 minute)
```bash
# Enqueue multiple jobs
for i in {1..5}; do
  queuectl enqueue "{\"id\":\"job$i\",\"command\":\"sleep 1 && echo Job $i\"}"
done

# Start 3 workers
queuectl worker start --count 3

# Show status
queuectl status

# Wait for jobs to complete, then show completed jobs
queuectl list --state completed

# Stop workers
queuectl worker stop
```

### 4. Retry and DLQ (2 minutes)
```bash
# Enqueue a failing job
queuectl enqueue '{"id":"fail1","command":"nonexistentcommand123","max_retries":2}'

# Start worker
queuectl worker start --count 1

# Wait for retries (show status periodically)
queuectl status

# After retries exhausted, show DLQ
queuectl dlq list

# Retry from DLQ
queuectl dlq retry fail1

# Check it's back in pending
queuectl list --state pending

# Stop worker
queuectl worker stop
```

### 5. Configuration (30 seconds)
```bash
# Show current config
queuectl config get

# Set new config
queuectl config set max-retries 5
queuectl config set backoff-base 3

# Verify
queuectl config get
```

### 6. Persistence (30 seconds)
```bash
# Enqueue a job
queuectl enqueue '{"id":"persist1","command":"echo Persistence Test"}'

# Stop everything
queuectl worker stop

# Show job still exists
queuectl list --state pending

# Restart worker
queuectl worker start --count 1

# Show job gets processed
queuectl list --state completed
```

**Total Demo Time: ~6-7 minutes**

## Final Checklist

- [ ] Git repository initialized
- [ ] All files committed
- [ ] GitHub repository created (public)
- [ ] Code pushed to GitHub
- [ ] Demo video recorded
- [ ] Demo video uploaded to Google Drive
- [ ] Drive link updated in README.md
- [ ] Repository link ready to share

## Sharing the Repository

Once everything is set up, share the GitHub repository link:

```
https://github.com/YOUR_USERNAME/queuectl
```

