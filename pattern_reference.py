#!/usr/bin/env python3
"""
Quick reference: List all security patterns by severity
Usage: python3 pattern_reference.py [severity]
Example: python3 pattern_reference.py critical
"""

import sys
from security_config import DESTRUCTIVE_PATTERNS, SEVERITY_INFO

def show_patterns(filter_severity=None):
    """Display patterns, optionally filtered by severity"""
    
    if filter_severity:
        print(f"\n{'='*70}")
        emoji = SEVERITY_INFO[filter_severity]["emoji"]
        print(f"  {emoji} {filter_severity.upper()} SEVERITY PATTERNS")
        print(f"  {SEVERITY_INFO[filter_severity]['description']}")
        print('='*70 + "\n")
        
        patterns = [(p, i) for p, i in DESTRUCTIVE_PATTERNS.items() 
                   if i['severity'] == filter_severity]
        
        for pattern, info in sorted(patterns):
            print(f"  • {pattern:35s} - {info['description']}")
        
        print(f"\n  Total: {len(patterns)} patterns\n")
    else:
        print("\n" + "="*70)
        print("  🔒 ALL DESTRUCTIVE PATTERNS BY SEVERITY")
        print("="*70 + "\n")
        
        for severity in ['critical', 'high', 'medium', 'low']:
            patterns = [(p, i) for p, i in DESTRUCTIVE_PATTERNS.items() 
                       if i['severity'] == severity]
            
            if patterns:
                emoji = SEVERITY_INFO[severity]["emoji"]
                print(f"{emoji} {severity.upper()} ({len(patterns)} patterns)")
                for pattern, info in sorted(patterns)[:5]:  # Show first 5
                    print(f"   • {pattern:30s} - {info['description']}")
                if len(patterns) > 5:
                    print(f"   ... and {len(patterns) - 5} more")
                print()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        severity = sys.argv[1].lower()
        if severity in ['critical', 'high', 'medium', 'low']:
            show_patterns(severity)
        else:
            print(f"Unknown severity: {severity}")
            print("Valid options: critical, high, medium, low")
    else:
        show_patterns()
