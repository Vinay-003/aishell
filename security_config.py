"""
Cliffy Security Configuration
Comprehensive list of destructive and potentially dangerous commands
"""

# ============================================================================
# DESTRUCTIVE COMMAND PATTERNS
# Pattern-based detection for known dangerous operations
# ============================================================================

DESTRUCTIVE_PATTERNS = {
    # ========================================================================
    # FILE DELETION - CRITICAL/HIGH RISK
    # ========================================================================
    "rm -rf": {
        "severity": "critical",
        "description": "Recursive forced deletion (no confirmation)",
        "category": "file_deletion"
    },
    "rm -fr": {
        "severity": "critical",
        "description": "Recursive forced deletion (no confirmation)",
        "category": "file_deletion"
    },
    "rm -r": {
        "severity": "high",
        "description": "Recursive deletion",
        "category": "file_deletion"
    },
    "rm -f": {
        "severity": "high",
        "description": "Forced deletion without confirmation",
        "category": "file_deletion"
    },
    "shred": {
        "severity": "critical",
        "description": "Secure file deletion (unrecoverable)",
        "category": "file_deletion"
    },
    "wipefs": {
        "severity": "critical",
        "description": "Wipe filesystem signatures",
        "category": "file_deletion"
    },
    "srm": {
        "severity": "critical",
        "description": "Secure removal (unrecoverable)",
        "category": "file_deletion"
    },
    
    # ========================================================================
    # DISK OPERATIONS - CRITICAL RISK
    # ========================================================================
    "dd if=": {
        "severity": "critical",
        "description": "Direct disk read/write operation",
        "category": "disk_operations"
    },
    "dd of=/dev/": {
        "severity": "critical",
        "description": "Writing directly to device (data loss)",
        "category": "disk_operations"
    },
    "mkfs": {
        "severity": "critical",
        "description": "Format filesystem (destroys all data)",
        "category": "disk_operations"
    },
    "mkfs.ext": {
        "severity": "critical",
        "description": "Format filesystem (destroys all data)",
        "category": "disk_operations"
    },
    "mkfs.ntfs": {
        "severity": "critical",
        "description": "Format filesystem (destroys all data)",
        "category": "disk_operations"
    },
    "fdisk": {
        "severity": "critical",
        "description": "Disk partitioning tool (can destroy data)",
        "category": "disk_operations"
    },
    "parted": {
        "severity": "critical",
        "description": "Partition editor (can destroy data)",
        "category": "disk_operations"
    },
    "gdisk": {
        "severity": "critical",
        "description": "GPT partition editor (can destroy data)",
        "category": "disk_operations"
    },
    
    # ========================================================================
    # DATA OVERWRITE - CRITICAL/HIGH RISK
    # ========================================================================
    "> /dev/sd": {
        "severity": "critical",
        "description": "Direct write to storage device",
        "category": "data_overwrite"
    },
    "> /dev/hd": {
        "severity": "critical",
        "description": "Direct write to storage device",
        "category": "data_overwrite"
    },
    "> /dev/nvme": {
        "severity": "critical",
        "description": "Direct write to NVMe device",
        "category": "data_overwrite"
    },
    "cat /dev/zero >": {
        "severity": "critical",
        "description": "Overwrite with zeros (data destruction)",
        "category": "data_overwrite"
    },
    "cat /dev/random >": {
        "severity": "critical",
        "description": "Overwrite with random data (data destruction)",
        "category": "data_overwrite"
    },
    "cat /dev/urandom >": {
        "severity": "critical",
        "description": "Overwrite with random data (data destruction)",
        "category": "data_overwrite"
    },
    ": > ": {
        "severity": "high",
        "description": "Truncate file to zero size (data loss)",
        "category": "data_overwrite"
    },
    "truncate -s 0": {
        "severity": "high",
        "description": "Truncate file to zero bytes",
        "category": "data_overwrite"
    },
    
    # ========================================================================
    # SYSTEM CONTROL - HIGH/MEDIUM RISK
    # ========================================================================
    "systemctl stop": {
        "severity": "high",
        "description": "Stop system service (service interruption)",
        "category": "system_control"
    },
    "systemctl disable": {
        "severity": "high",
        "description": "Disable system service (won't start on boot)",
        "category": "system_control"
    },
    "systemctl mask": {
        "severity": "high",
        "description": "Mask service (prevents starting)",
        "category": "system_control"
    },
    "service stop": {
        "severity": "high",
        "description": "Stop service (service interruption)",
        "category": "system_control"
    },
    "shutdown": {
        "severity": "high",
        "description": "System shutdown",
        "category": "system_control"
    },
    "reboot": {
        "severity": "high",
        "description": "System reboot",
        "category": "system_control"
    },
    "halt": {
        "severity": "high",
        "description": "Halt system",
        "category": "system_control"
    },
    "poweroff": {
        "severity": "high",
        "description": "Power off system",
        "category": "system_control"
    },
    "init 0": {
        "severity": "high",
        "description": "Shutdown system",
        "category": "system_control"
    },
    "init 6": {
        "severity": "high",
        "description": "Reboot system",
        "category": "system_control"
    },
    "kill -9": {
        "severity": "medium",
        "description": "Force kill process (may cause data loss)",
        "category": "system_control"
    },
    "killall -9": {
        "severity": "high",
        "description": "Force kill all matching processes",
        "category": "system_control"
    },
    "pkill -9": {
        "severity": "high",
        "description": "Force kill processes by pattern",
        "category": "system_control"
    },
    
    # ========================================================================
    # PERMISSIONS - HIGH/MEDIUM RISK
    # ========================================================================
    "chmod -R 777": {
        "severity": "high",
        "description": "Recursive: Make all files world-writable (security risk)",
        "category": "permissions"
    },
    "chmod -R 000": {
        "severity": "high",
        "description": "Recursive: Remove all permissions (system unusable)",
        "category": "permissions"
    },
    "chmod 000": {
        "severity": "medium",
        "description": "Remove all permissions (file inaccessible)",
        "category": "permissions"
    },
    "chown -R": {
        "severity": "medium",
        "description": "Recursive ownership change",
        "category": "permissions"
    },
    "chgrp -R": {
        "severity": "medium",
        "description": "Recursive group change",
        "category": "permissions"
    },
    "chmod -R +x": {
        "severity": "medium",
        "description": "Recursive: Make all files executable (security risk)",
        "category": "permissions"
    },
    
    # ========================================================================
    # PACKAGE MANAGEMENT - MEDIUM RISK
    # ========================================================================
    "apt-get remove": {
        "severity": "medium",
        "description": "Remove package (may break dependencies)",
        "category": "package_mgmt"
    },
    "apt-get purge": {
        "severity": "medium",
        "description": "Remove package with config files",
        "category": "package_mgmt"
    },
    "apt remove": {
        "severity": "medium",
        "description": "Remove package (may break dependencies)",
        "category": "package_mgmt"
    },
    "apt purge": {
        "severity": "medium",
        "description": "Remove package with config files",
        "category": "package_mgmt"
    },
    "apt autoremove": {
        "severity": "medium",
        "description": "Remove unused packages (may remove needed packages)",
        "category": "package_mgmt"
    },
    "yum remove": {
        "severity": "medium",
        "description": "Remove package (may break dependencies)",
        "category": "package_mgmt"
    },
    "dnf remove": {
        "severity": "medium",
        "description": "Remove package (may break dependencies)",
        "category": "package_mgmt"
    },
    "pacman -R": {
        "severity": "medium",
        "description": "Remove package (may break dependencies)",
        "category": "package_mgmt"
    },
    "pip uninstall": {
        "severity": "low",
        "description": "Remove Python package",
        "category": "package_mgmt"
    },
    "npm uninstall -g": {
        "severity": "low",
        "description": "Remove global npm package",
        "category": "package_mgmt"
    },
    
    # ========================================================================
    # GIT OPERATIONS - HIGH/MEDIUM RISK
    # ========================================================================
    "git reset --hard": {
        "severity": "high",
        "description": "Hard reset (discards uncommitted changes)",
        "category": "git_operations"
    },
    "git clean -fd": {
        "severity": "medium",
        "description": "Remove untracked files and directories",
        "category": "git_operations"
    },
    "git clean -fdx": {
        "severity": "high",
        "description": "Remove untracked and ignored files",
        "category": "git_operations"
    },
    "git push -f": {
        "severity": "high",
        "description": "Force push (rewrites remote history)",
        "category": "git_operations"
    },
    "git push --force": {
        "severity": "high",
        "description": "Force push (rewrites remote history)",
        "category": "git_operations"
    },
    "git branch -D": {
        "severity": "medium",
        "description": "Force delete branch (may lose commits)",
        "category": "git_operations"
    },
    "git rebase": {
        "severity": "medium",
        "description": "Rewrite commit history",
        "category": "git_operations"
    },
    "git filter-branch": {
        "severity": "high",
        "description": "Rewrite repository history (destructive)",
        "category": "git_operations"
    },
    
    # ========================================================================
    # DATABASE OPERATIONS - CRITICAL/HIGH RISK
    # ========================================================================
    "DROP DATABASE": {
        "severity": "critical",
        "description": "Delete entire database",
        "category": "database"
    },
    "DROP TABLE": {
        "severity": "high",
        "description": "Delete table (data loss)",
        "category": "database"
    },
    "TRUNCATE": {
        "severity": "high",
        "description": "Delete all table data",
        "category": "database"
    },
    "DELETE FROM": {
        "severity": "medium",
        "description": "Delete rows from table",
        "category": "database"
    },
    "DROP SCHEMA": {
        "severity": "high",
        "description": "Delete database schema",
        "category": "database"
    },
    "DROP INDEX": {
        "severity": "medium",
        "description": "Delete database index",
        "category": "database"
    },
    
    # ========================================================================
    # DOCKER/CONTAINER OPERATIONS - MEDIUM RISK
    # ========================================================================
    "docker rm -f": {
        "severity": "medium",
        "description": "Force remove container (data loss)",
        "category": "docker"
    },
    "docker rmi -f": {
        "severity": "medium",
        "description": "Force remove image",
        "category": "docker"
    },
    "docker system prune -a": {
        "severity": "high",
        "description": "Remove all unused containers, networks, images",
        "category": "docker"
    },
    "docker volume rm": {
        "severity": "medium",
        "description": "Remove docker volume (data loss)",
        "category": "docker"
    },
    "kubectl delete": {
        "severity": "medium",
        "description": "Delete Kubernetes resources",
        "category": "docker"
    },
    
    # ========================================================================
    # NETWORK OPERATIONS - MEDIUM RISK
    # ========================================================================
    "iptables -F": {
        "severity": "high",
        "description": "Flush all firewall rules (security risk)",
        "category": "network"
    },
    "iptables -X": {
        "severity": "high",
        "description": "Delete all firewall chains",
        "category": "network"
    },
    "ufw disable": {
        "severity": "high",
        "description": "Disable firewall (security risk)",
        "category": "network"
    },
    "ip link delete": {
        "severity": "medium",
        "description": "Delete network interface",
        "category": "network"
    },
    
    # ========================================================================
    # MALICIOUS/DANGEROUS PATTERNS - CRITICAL RISK
    # ========================================================================
    ":(){ :|:& };:": {
        "severity": "critical",
        "description": "Fork bomb (system crash)",
        "category": "malicious"
    },
    "wget | sh": {
        "severity": "critical",
        "description": "Download and execute unknown script",
        "category": "malicious"
    },
    "curl | sh": {
        "severity": "critical",
        "description": "Download and execute unknown script",
        "category": "malicious"
    },
    "curl | bash": {
        "severity": "critical",
        "description": "Download and execute unknown script",
        "category": "malicious"
    },
    "wget | bash": {
        "severity": "critical",
        "description": "Download and execute unknown script",
        "category": "malicious"
    },
    "eval $(curl": {
        "severity": "critical",
        "description": "Execute downloaded code",
        "category": "malicious"
    },
    "> /dev/sda": {
        "severity": "critical",
        "description": "Write to main disk (data destruction)",
        "category": "malicious"
    },
    "mv * /dev/null": {
        "severity": "critical",
        "description": "Move all files to null device (delete all)",
        "category": "malicious"
    },
    "rm -rf /": {
        "severity": "critical",
        "description": "Delete entire filesystem",
        "category": "malicious"
    },
    "rm -rf /*": {
        "severity": "critical",
        "description": "Delete entire filesystem",
        "category": "malicious"
    },
    "rm -rf $HOME": {
        "severity": "critical",
        "description": "Delete home directory",
        "category": "malicious"
    },
}

# ============================================================================
# AI ANALYSIS TRIGGERS
# Commands that should be analyzed by AI if not caught by patterns
# ============================================================================

AI_CHECK_TRIGGERS = {
    # File operations that can overwrite/delete
    "rm": "File deletion",
    "mv": "Move/rename (can overwrite existing files)",
    "cp": "Copy (can overwrite existing files)",
    "dd": "Low-level copy (can overwrite)",
    "rsync": "Sync (can delete with --delete flag)",
    
    # Data manipulation
    "truncate": "File truncation (data loss)",
    "shred": "Secure deletion",
    "format": "Formatting operations",
    "wipe": "Data wiping",
    
    # Redirection that overwrites
    ">": "Output redirection (overwrites file)",
    "tee": "Write to file (can overwrite)",
    
    # System operations
    "kill": "Process termination",
    "pkill": "Pattern-based process kill",
    "killall": "Kill all matching processes",
    
    # Compression (can overwrite)
    "tar": "Archive operations (can overwrite)",
    "zip": "Compression (can overwrite)",
    "unzip": "Extraction (can overwrite)",
    "gzip": "Compression (can overwrite)",
    
    # Windows-style commands
    "del": "Delete (Windows)",
    "erase": "Erase (Windows)",
    "format": "Format (Windows)",
    "deltree": "Delete tree (Windows)",
}

# ============================================================================
# SEVERITY LEVELS
# ============================================================================

SEVERITY_INFO = {
    "critical": {
        "emoji": "🔴",
        "color": "\033[91m",  # Red
        "description": "System-threatening operations that can cause total data loss"
    },
    "high": {
        "emoji": "🟠",
        "color": "\033[93m",  # Yellow
        "description": "High-risk operations that can cause significant data loss or disruption"
    },
    "medium": {
        "emoji": "🟡",
        "color": "\033[33m",  # Orange
        "description": "Medium-risk operations that may cause issues or require attention"
    },
    "low": {
        "emoji": "🟢",
        "color": "\033[92m",  # Green
        "description": "Low-risk operations that are generally safe"
    }
}

# ============================================================================
# SAFE COMMAND WHITELIST
# ============================================================================
# NOTE: This whitelist is NOT used to bypass safety checks!
# It's used for optimization and documentation purposes only.
#
# WHY? Because safe commands can become dangerous with operators:
#   - "echo test > file.txt" - OVERWRITES file
#   - "ls && rm -rf /" - CHAINS dangerous command
#   - "cat file | sh" - PIPES to shell execution
#
# The security system ALWAYS checks for dangerous patterns and operators
# REGARDLESS of the base command. This whitelist serves to:
#   1. Document which base commands are inherently safe
#   2. Potential future optimization (skip AI for simple safe commands)
#   3. Help users understand what's considered safe
#
# Current behavior: All commands are checked for dangerous patterns/operators first.
# ============================================================================

SAFE_COMMANDS = {
    "ls", "ll", "la", "pwd", "cd", "cat", "less", "more", "head", "tail",
    "grep", "find", "which", "whereis", "whoami", "id", "date", "cal", "uptime",
    "df", "du", "free", "top", "htop", "ps", "pstree", "man", "info", "help",
    "history", "alias", "type", "file", "stat", "wc", "sort", "uniq", "diff",
    "tar -tz", "tar -tzv", "tar -tf",  # Listing only
    "git status", "git log", "git show", "git diff", "git branch",  # Read-only git
    "docker ps", "docker images", "docker inspect",  # Read-only docker
}
