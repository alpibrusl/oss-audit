#!/usr/bin/env bash
# Examples for: list

# List the latest 20 audits
oss-audit list

# List 50 audits as JSON for an agent
oss-audit list -n 50 --output json
