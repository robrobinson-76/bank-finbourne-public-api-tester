# Bank FINBOURNE API Tester: MCP Agents Guide

> **Status:** Scaffold — to be completed from plan.

## Overview

The **bank-finbourne** MCP server provides read-only tools for querying FINBOURNE LUSID data across portfolios, instruments, transactions, holdings, and reference data.

## Key Points for Agent Usage

**Tool Naming:** Tools follow snake_case patterns like `get_portfolio`, `list_portfolios`, `get_transactions`. Singular tools require an ID; plural tools accept filter parameters and support pagination.

**Parameter Formats:** Dates must be ISO 8601 format (`"YYYY-MM-DDThh:mm:ssZ"`). IDs are opaque strings discovered from query results.

**Error Handling:** Tools return error objects as dictionaries rather than exceptions. Check for an `"error"` key to detect failures.

**Scope Limitations:** The server is read-only. No mutations, no cross-portfolio aggregation without explicit tool support.

## Tool Reference

To be populated from plan.
