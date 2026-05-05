#!/usr/bin/env bash
# Examples for: audit

# Audit a remote GitHub repo
rubric audit https://github.com/alpibrusl/lex-lang

# Audit a local repo, technical pillar only
rubric audit . --skip-business --skip-community

# Get a structured envelope for an agent
rubric audit . --skip-business --skip-community --output json
